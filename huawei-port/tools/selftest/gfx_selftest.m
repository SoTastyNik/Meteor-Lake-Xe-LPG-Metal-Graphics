// gfx_selftest: correctness oracles for the MateBook graphics stack. Each check draws or computes something whose right
// answer is known (computed on the CPU, or by Apple's own software renderers), compares, and prints one line:
//   TEST <name>: PASS|FAIL|SKIP <detail>
// The checks follow the classes of bugs this port has met: ordering between GPU passes (Photo Booth bands), a sampler a
// shader parked in an app's slot (mosaic), mip levels (Dock badge), format views of one image (screen sharing), shader
// writes to sRGB (OBS), CoreImage and OpenGL against Apple's CPU renderers (any app on them, image orientation), and
// a VideoToolbox encode/decode round trip (calls, screen sharing).
// build: clang -fobjc-arc -O1 gfx_selftest.m -o gfx_selftest -framework Metal -framework Foundation -framework IOSurface
//        -framework CoreVideo -framework CoreImage -framework OpenGL -framework VideoToolbox -framework CoreMedia
//        -framework ImageIO -framework CoreGraphics
// usage: gfx_selftest [name-substring ...]     SELFTEST_OUT=dir saves the images of a failed comparison there
#define GL_SILENCE_DEPRECATION 1
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <IOSurface/IOSurface.h>
#import <CoreVideo/CoreVideo.h>
#import <CoreImage/CoreImage.h>
#import <CoreGraphics/CoreGraphics.h>
#import <ImageIO/ImageIO.h>
#import <VideoToolbox/VideoToolbox.h>
#import <CoreMedia/CoreMedia.h>
#import <OpenGL/OpenGL.h>
#import <OpenGL/gl.h>
#import <OpenGL/glext.h>
#import <OpenGL/CGLIOSurface.h>
#include <math.h>
#include <dlfcn.h>

static id<MTLDevice> D;
static id<MTLCommandQueue> Q;
static id<MTLLibrary> L;
static int g_pass, g_fail, g_skip;
static int g_argc; static char **g_argv;

enum { PASS = 0, FAIL = 1, SKIP = 2 };
static void report(const char *name, int st, NSString *detail)
{
    const char *s = st == PASS ? "PASS" : st == FAIL ? "FAIL" : "SKIP";
    printf("TEST %s: %s %s\n", name, s, detail ? detail.UTF8String : "");
    fflush(stdout);
    if (st == PASS) g_pass++; else if (st == FAIL) g_fail++; else g_skip++;
}
static BOOL wanted(const char *name)
{
    if (g_argc < 2) return YES;
    for (int i = 1; i < g_argc; i++) if (strstr(name, g_argv[i])) return YES;
    return NO;
}
// an RGBA8 image (rows top to bottom) as PNG into $SELFTEST_OUT
static void save_png(const char *name, const uint8_t *rgba, int w, int h, size_t row)
{
    const char *dir = getenv("SELFTEST_OUT");
    if (!dir || !rgba) return;
    CGColorSpaceRef cs = CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
    CGContextRef c = CGBitmapContextCreate((void *)rgba, w, h, 8, row, cs, kCGImageAlphaPremultipliedLast);
    CGImageRef img = c ? CGBitmapContextCreateImage(c) : NULL;
    NSURL *url = [NSURL fileURLWithPath:[NSString stringWithFormat:@"%s/%s.png", dir, name]];
    CGImageDestinationRef dst = img ? CGImageDestinationCreateWithURL((__bridge CFURLRef)url, CFSTR("public.png"), 1, NULL) : NULL;
    if (dst) { CGImageDestinationAddImage(dst, img, NULL); CGImageDestinationFinalize(dst); CFRelease(dst); }
    if (img) CGImageRelease(img);
    if (c) CGContextRelease(c);
    CGColorSpaceRelease(cs);
}
static id<MTLComputePipelineState> cps(NSString *fn)
{
    NSError *e = nil;
    id<MTLFunction> f = [L newFunctionWithName:fn];
    id<MTLComputePipelineState> p = f ? [D newComputePipelineStateWithFunction:f error:&e] : nil;
    if (!p) printf("  (compute pipeline %s: %s)\n", fn.UTF8String, e ? e.description.UTF8String : "no function");
    return p;
}
static id<MTLRenderPipelineState> rps(NSString *vs, NSString *fs, MTLPixelFormat fmt)
{
    MTLRenderPipelineDescriptor *d = [MTLRenderPipelineDescriptor new];
    d.vertexFunction = [L newFunctionWithName:vs]; d.fragmentFunction = [L newFunctionWithName:fs];
    d.colorAttachments[0].pixelFormat = fmt;
    NSError *e = nil;
    id<MTLRenderPipelineState> p = (d.vertexFunction && d.fragmentFunction) ? [D newRenderPipelineStateWithDescriptor:d error:&e] : nil;
    if (!p) printf("  (render pipeline %s/%s: %s)\n", vs.UTF8String, fs.UTF8String, e ? e.description.UTF8String : "no function");
    return p;
}

static NSString *const kSrc = @"#include <metal_stdlib>\nusing namespace metal;\n"
    // chain: each dispatch reads its neighbour's value from the previous one; a missing barrier reads a half-updated source
    "kernel void chain_step(device const uint *src [[buffer(0)]], device uint *dst [[buffer(1)]], constant uint &k [[buffer(2)]],\n"
    "                       constant uint &n [[buffer(3)]], uint i [[thread_position_in_grid]]) {\n"
    "    if (i >= n) return; dst[i] = src[(i + 1u) % n] * 1664525u + k; }\n"
    "struct VOut { float4 pos [[position]]; };\n"
    "vertex VOut fs_tri(uint vid [[vertex_id]]) { float2 p = float2((vid << 1) & 2, vid & 2); VOut o; o.pos = float4(p * 2.0 - 1.0, 0, 1); return o; }\n"
    "fragment float4 rt_pattern(VOut in [[stage_in]]) { uint2 p = uint2(in.pos.xy);\n"
    "    return float4(float(p.x & 255u) / 255.0, float(p.y & 255u) / 255.0, float((p.x ^ p.y) & 255u) / 255.0, 1.0); }\n"
    "kernel void tex_to_buf(texture2d<float, access::read> t [[texture(0)]], device uchar4 *out [[buffer(0)]], uint2 p [[thread_position_in_grid]]) {\n"
    "    if (p.x >= t.get_width() || p.y >= t.get_height()) return; float4 c = t.read(p); out[p.y * t.get_width() + p.x] = uchar4(c * 255.0 + 0.5); }\n"
    "fragment float4 app_sampler(VOut in [[stage_in]], texture2d<float> t [[texture(0)]], sampler s [[sampler(0)]], constant float2 &size [[buffer(0)]]) {\n"
    "    return t.sample(s, in.pos.xy / size); }\n"
    "fragment float4 own_sampler(VOut in [[stage_in]], texture2d<float> t [[texture(0)]], constant float2 &size [[buffer(0)]]) {\n"
    "    constexpr sampler ns(filter::nearest, address::clamp_to_edge); return t.sample(ns, in.pos.xy / size) * 0.5; }\n"
    "kernel void sample_level(texture2d<float> t [[texture(0)]], sampler s [[sampler(0)]], device float4 *out [[buffer(0)]],\n"
    "                         constant float &lvl [[buffer(1)]], uint i [[thread_position_in_grid]]) {\n"
    "    if (i == 0) out[0] = t.sample(s, float2(0.5, 0.5), level(lvl)); }\n"
    "kernel void write_srgb(texture2d<float, access::write> t [[texture(0)]], uint2 p [[thread_position_in_grid]]) {\n"
    "    if (p.x >= t.get_width() || p.y >= t.get_height()) return; t.write(float4(0.5, 0.25, 1.0, 1.0), p); }\n"
    // v72: pixel coordinates (OpenGL's rectangle textures through Metal), with the app's sampler and with the shader's own
    "fragment float4 px_app(VOut in [[stage_in]], texture2d<float> t [[texture(0)]], sampler s [[sampler(0)]]) { return t.sample(s, in.pos.xy); }\n"
    "fragment float4 px_own(VOut in [[stage_in]], texture2d<float> t [[texture(0)]]) {\n"
    "    constexpr sampler ps(coord::pixel, filter::nearest, address::clamp_to_edge); return t.sample(ps, in.pos.xy); }\n"
    "kernel void tex_size(texture2d<float> t [[texture(0)]], device uint *out [[buffer(0)]], uint i [[thread_position_in_grid]]) {\n"
    "    if (i == 0) { out[0] = t.get_width(); out[1] = t.get_height(); } }\n";

// ---- 1. compute chains: serial encoder, and a concurrent encoder with memory barriers ------------------------------------
static void test_chain(const char *name, BOOL concurrent, BOOL split)
{
    if (!wanted(name)) return;
    id<MTLComputePipelineState> p = cps(@"chain_step");
    if (!p) { report(name, FAIL, @"pipeline"); return; }
    const uint32_t n = 1u << 18, steps = 48;
    id<MTLBuffer> a = [D newBufferWithLength:n * 4 options:MTLResourceStorageModeShared], b = [D newBufferWithLength:n * 4 options:MTLResourceStorageModeShared];
    uint32_t *ref = malloc(n * 4), *tmp = malloc(n * 4);
    for (uint32_t i = 0; i < n; i++) ((uint32_t *)a.contents)[i] = ref[i] = i * 2654435761u;
    for (uint32_t k = 0; k < steps; k++) {
        for (uint32_t i = 0; i < n; i++) tmp[i] = ref[(i + 1) % n] * 1664525u + k;
        memcpy(ref, tmp, n * 4);
    }
    id<MTLCommandBuffer> cb = [Q commandBuffer];
    id<MTLComputeCommandEncoder> e = concurrent ? [cb computeCommandEncoderWithDispatchType:MTLDispatchTypeConcurrent] : [cb computeCommandEncoder];
    [e setComputePipelineState:p];
    for (uint32_t k = 0; k < steps; k++) {
        if (split && k && k % 8 == 0) {   // a few encoders in one command buffer: ordering between encoders too
            [e endEncoding];
            e = concurrent ? [cb computeCommandEncoderWithDispatchType:MTLDispatchTypeConcurrent] : [cb computeCommandEncoder];
            [e setComputePipelineState:p];
        }
        id<MTLBuffer> src = (k & 1) ? b : a, dst = (k & 1) ? a : b;
        [e setBuffer:src offset:0 atIndex:0]; [e setBuffer:dst offset:0 atIndex:1];
        [e setBytes:&k length:4 atIndex:2]; [e setBytes:&n length:4 atIndex:3];
        [e dispatchThreads:MTLSizeMake(n, 1, 1) threadsPerThreadgroup:MTLSizeMake(256, 1, 1)];
        if (concurrent) [e memoryBarrierWithScope:MTLBarrierScopeBuffers];
    }
    [e endEncoding]; [cb commit]; [cb waitUntilCompleted];
    const uint32_t *got = (steps & 1) ? b.contents : a.contents;
    uint32_t wrong = 0, first = UINT32_MAX;
    for (uint32_t i = 0; i < n; i++) if (got[i] != ref[i]) { wrong++; if (first == UINT32_MAX) first = i; }
    free(ref); free(tmp);
    report(name, cb.error ? FAIL : wrong ? FAIL : PASS,
           cb.error ? cb.error.localizedDescription : [NSString stringWithFormat:@"%u of %u values wrong (first at %u), %u dispatches", wrong, n, first == UINT32_MAX ? 0 : first, steps]);
}

// ---- 2. a render pass, then a compute pass reading its target in the same command buffer --------------------------------
static void test_render_then_compute(void)
{
    const char *name = "render-then-compute";
    if (!wanted(name)) return;
    const int W = 300, H = 200;
    id<MTLRenderPipelineState> rp = rps(@"fs_tri", @"rt_pattern", MTLPixelFormatRGBA8Unorm);
    id<MTLComputePipelineState> cp = cps(@"tex_to_buf");
    if (!rp || !cp) { report(name, FAIL, @"pipeline"); return; }
    MTLTextureDescriptor *td = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm width:W height:H mipmapped:NO];
    td.usage = MTLTextureUsageRenderTarget | MTLTextureUsageShaderRead; td.storageMode = MTLStorageModePrivate;
    id<MTLTexture> t = [D newTextureWithDescriptor:td];
    id<MTLBuffer> out = [D newBufferWithLength:W * H * 4 options:MTLResourceStorageModeShared];
    memset(out.contents, 0, W * H * 4);
    unsigned wrong = 0;
    for (int round = 0; round < 20; round++) {
        id<MTLCommandBuffer> cb = [Q commandBuffer];
        MTLRenderPassDescriptor *rd = [MTLRenderPassDescriptor renderPassDescriptor];
        rd.colorAttachments[0].texture = t; rd.colorAttachments[0].loadAction = MTLLoadActionClear;
        rd.colorAttachments[0].clearColor = MTLClearColorMake(1, 0, 1, 1); rd.colorAttachments[0].storeAction = MTLStoreActionStore;
        id<MTLRenderCommandEncoder> re = [cb renderCommandEncoderWithDescriptor:rd];
        [re setRenderPipelineState:rp]; [re drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3]; [re endEncoding];
        id<MTLComputeCommandEncoder> ce = [cb computeCommandEncoder];
        [ce setComputePipelineState:cp]; [ce setTexture:t atIndex:0]; [ce setBuffer:out offset:0 atIndex:0];
        [ce dispatchThreads:MTLSizeMake(W, H, 1) threadsPerThreadgroup:MTLSizeMake(16, 16, 1)]; [ce endEncoding];
        [cb commit]; [cb waitUntilCompleted];
        const uint8_t *px = out.contents;
        for (int y = 0; y < H; y++) for (int x = 0; x < W; x++) {
            const uint8_t *q = px + (y * W + x) * 4;
            if (q[0] != (x & 255) || q[1] != (y & 255) || q[2] != ((x ^ y) & 255) || q[3] != 255) wrong++;
        }
        if (wrong) { save_png("render-then-compute", px, W, H, W * 4); break; }
    }
    report(name, wrong ? FAIL : PASS, [NSString stringWithFormat:@"%u wrong pixels over 20 rounds", wrong]);
}

// ---- 3. a shader with its own constexpr sampler must give the app's sampler back (the Dock/Control Center mosaic) -------
static void test_sampler_park(void)
{
    const char *name = "sampler-restore";
    if (!wanted(name)) return;
    const int W = 64, H = 64;
    id<MTLRenderPipelineState> app = rps(@"fs_tri", @"app_sampler", MTLPixelFormatRGBA8Unorm), own = rps(@"fs_tri", @"own_sampler", MTLPixelFormatRGBA8Unorm);
    id<MTLComputePipelineState> cp = cps(@"tex_to_buf");
    if (!app || !own || !cp) { report(name, FAIL, @"pipeline"); return; }
    MTLTextureDescriptor *sd = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm width:2 height:2 mipmapped:NO];
    id<MTLTexture> src = [D newTextureWithDescriptor:sd];
    const uint8_t checker[16] = { 0,0,0,255, 255,255,255,255, 255,255,255,255, 0,0,0,255 };
    [src replaceRegion:MTLRegionMake2D(0, 0, 2, 2) mipmapLevel:0 withBytes:checker bytesPerRow:8];
    MTLTextureDescriptor *td = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm width:W height:H mipmapped:NO];
    td.usage = MTLTextureUsageRenderTarget | MTLTextureUsageShaderRead; td.storageMode = MTLStorageModePrivate;
    id<MTLTexture> t = [D newTextureWithDescriptor:td];
    MTLSamplerDescriptor *ld = [MTLSamplerDescriptor new];
    ld.minFilter = ld.magFilter = MTLSamplerMinMagFilterLinear; ld.sAddressMode = ld.tAddressMode = MTLSamplerAddressModeClampToEdge;
    id<MTLSamplerState> linear = [D newSamplerStateWithDescriptor:ld];
    id<MTLBuffer> out = [D newBufferWithLength:W * H * 4 options:MTLResourceStorageModeShared];
    const float size[2] = { W, H };
    id<MTLCommandBuffer> cb = [Q commandBuffer];
    MTLRenderPassDescriptor *rd = [MTLRenderPassDescriptor renderPassDescriptor];
    rd.colorAttachments[0].texture = t; rd.colorAttachments[0].loadAction = MTLLoadActionClear; rd.colorAttachments[0].storeAction = MTLStoreActionStore;
    id<MTLRenderCommandEncoder> re = [cb renderCommandEncoderWithDescriptor:rd];
    [re setFragmentTexture:src atIndex:0]; [re setFragmentBytes:size length:8 atIndex:0];
    [re setFragmentSamplerState:linear atIndex:0];
    [re setRenderPipelineState:app]; [re drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];
    [re setRenderPipelineState:own]; [re drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];
    // Metal keeps the app's linear sampler bound at index 0: this draw must filter linearly again
    [re setRenderPipelineState:app]; [re drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];
    [re endEncoding];
    id<MTLComputeCommandEncoder> ce = [cb computeCommandEncoder];
    [ce setComputePipelineState:cp]; [ce setTexture:t atIndex:0]; [ce setBuffer:out offset:0 atIndex:0];
    [ce dispatchThreads:MTLSizeMake(W, H, 1) threadsPerThreadgroup:MTLSizeMake(8, 8, 1)]; [ce endEncoding];
    [cb commit]; [cb waitUntilCompleted];
    const uint8_t *px = out.contents; unsigned mid = 0;
    for (int i = 0; i < W * H; i++) if (px[i * 4] > 24 && px[i * 4] < 231) mid++;
    const double frac = (double)mid / (W * H);
    if (frac < 0.25) save_png("sampler-restore", px, W, H, W * 4);
    report(name, frac >= 0.25 ? PASS : FAIL, [NSString stringWithFormat:@"%.0f%% of pixels between black and white (linear filtering > 25%%, nearest blocks ~0%%)", frac * 100]);
}

// ---- 4. each mip level of a texture reads back as that level ----------------------------------------------------------
static void test_mips(void)
{
    const char *name = "mip-levels";
    if (!wanted(name)) return;
    id<MTLComputePipelineState> p = cps(@"sample_level");
    if (!p) { report(name, FAIL, @"pipeline"); return; }
    MTLTextureDescriptor *td = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm width:108 height:108 mipmapped:YES];
    id<MTLTexture> t = [D newTextureWithDescriptor:td];
    const NSUInteger levels = t.mipmapLevelCount;
    for (NSUInteger l = 0; l < levels; l++) {
        const NSUInteger w = MAX(1u, 108u >> l), h = w;
        uint8_t *buf = malloc(w * h * 4);
        for (NSUInteger i = 0; i < w * h; i++) { buf[i * 4] = (uint8_t)(l * 36); buf[i * 4 + 1] = (uint8_t)(255 - l * 36); buf[i * 4 + 2] = 128; buf[i * 4 + 3] = 255; }
        [t replaceRegion:MTLRegionMake2D(0, 0, w, h) mipmapLevel:l withBytes:buf bytesPerRow:w * 4];
        free(buf);
    }
    MTLSamplerDescriptor *sd = [MTLSamplerDescriptor new];
    sd.minFilter = sd.magFilter = MTLSamplerMinMagFilterNearest; sd.mipFilter = MTLSamplerMipFilterNearest;
    id<MTLSamplerState> s = [D newSamplerStateWithDescriptor:sd];
    id<MTLBuffer> out = [D newBufferWithLength:16 options:MTLResourceStorageModeShared];
    NSMutableString *bad = [NSMutableString string];
    for (NSUInteger l = 0; l < levels; l++) {
        const float lvl = (float)l;
        id<MTLCommandBuffer> cb = [Q commandBuffer]; id<MTLComputeCommandEncoder> e = [cb computeCommandEncoder];
        [e setComputePipelineState:p]; [e setTexture:t atIndex:0]; [e setSamplerState:s atIndex:0];
        [e setBuffer:out offset:0 atIndex:0]; [e setBytes:&lvl length:4 atIndex:1];
        [e dispatchThreads:MTLSizeMake(1, 1, 1) threadsPerThreadgroup:MTLSizeMake(1, 1, 1)]; [e endEncoding];
        [cb commit]; [cb waitUntilCompleted];
        const float *c = out.contents;
        if (fabsf(c[0] * 255 - l * 36) > 2 || fabsf(c[1] * 255 - (255 - l * 36)) > 2) [bad appendFormat:@" level %lu read %.0f,%.0f", (unsigned long)l, c[0] * 255, c[1] * 255];
    }
    report(name, bad.length ? FAIL : PASS, bad.length ? bad : [NSString stringWithFormat:@"%lu levels of a 108x108 texture", (unsigned long)levels]);
}

// ---- 5. one image viewed as another format of its size (screen capture views BGRA as RGBA) -----------------------------
static int view_check(id<MTLTexture> base, NSMutableString *bad, const char *what)
{
    id<MTLComputePipelineState> p = cps(@"tex_to_buf");
    id<MTLTexture> view = [base newTextureViewWithPixelFormat:MTLPixelFormatRGBA8Unorm];
    if (!p || !view) { [bad appendFormat:@" %s: no RGBA view", what]; return 1; }
    const NSUInteger W = base.width, H = base.height;
    id<MTLBuffer> a = [D newBufferWithLength:W * H * 4 options:MTLResourceStorageModeShared], b = [D newBufferWithLength:W * H * 4 options:MTLResourceStorageModeShared];
    id<MTLCommandBuffer> cb = [Q commandBuffer]; id<MTLComputeCommandEncoder> e = [cb computeCommandEncoder];
    [e setComputePipelineState:p];
    [e setTexture:base atIndex:0]; [e setBuffer:a offset:0 atIndex:0]; [e dispatchThreads:MTLSizeMake(W, H, 1) threadsPerThreadgroup:MTLSizeMake(8, 8, 1)];
    [e setTexture:view atIndex:0]; [e setBuffer:b offset:0 atIndex:0]; [e dispatchThreads:MTLSizeMake(W, H, 1) threadsPerThreadgroup:MTLSizeMake(8, 8, 1)];
    [e endEncoding]; [cb commit]; [cb waitUntilCompleted];
    const uint8_t *pa = a.contents, *pb = b.contents;
    // memory holds B=10 G=20 R=30 A=255: the BGRA texture reads (30,20,10), its RGBA view (10,20,30)
    if (pa[0] != 30 || pa[1] != 20 || pa[2] != 10 || pb[0] != 10 || pb[1] != 20 || pb[2] != 30) {
        [bad appendFormat:@" %s: BGRA read %u,%u,%u (want 30,20,10), RGBA view %u,%u,%u (want 10,20,30)", what, pa[0], pa[1], pa[2], pb[0], pb[1], pb[2]];
        return 1;
    }
    return 0;
}
static void test_views(void)
{
    const char *name = "format-views";
    if (!wanted(name)) return;
    NSMutableString *bad = [NSMutableString string];
    const int W = 32, H = 32;
    IOSurfaceRef s = IOSurfaceCreate((__bridge CFDictionaryRef)@{ (id)kIOSurfaceWidth: @(W), (id)kIOSurfaceHeight: @(H), (id)kIOSurfaceBytesPerElement: @4,
                                                                  (id)kIOSurfacePixelFormat: @((uint32_t)'BGRA') });
    IOSurfaceLock(s, 0, NULL);
    for (int y = 0; y < H; y++) { uint8_t *r = (uint8_t *)IOSurfaceGetBaseAddress(s) + y * IOSurfaceGetBytesPerRow(s);
        for (int x = 0; x < W; x++) { r[x * 4] = 10; r[x * 4 + 1] = 20; r[x * 4 + 2] = 30; r[x * 4 + 3] = 255; } }
    IOSurfaceUnlock(s, 0, NULL);
    MTLTextureDescriptor *td = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatBGRA8Unorm width:W height:H mipmapped:NO];
    td.usage = MTLTextureUsageShaderRead | MTLTextureUsagePixelFormatView; td.storageMode = MTLStorageModeShared;
    id<MTLTexture> st = [D newTextureWithDescriptor:td iosurface:s plane:0];
    if (!st) [bad appendString:@" IOSurface texture: nil"]; else view_check(st, bad, "IOSurface");
    const NSUInteger align = [D minimumLinearTextureAlignmentForPixelFormat:MTLPixelFormatBGRA8Unorm];
    const NSUInteger bpr = (W * 4 + align - 1) / align * align;
    id<MTLBuffer> buf = [D newBufferWithLength:bpr * H options:MTLResourceStorageModeShared];
    for (int y = 0; y < H; y++) { uint8_t *r = (uint8_t *)buf.contents + y * bpr; for (int x = 0; x < W; x++) { r[x * 4] = 10; r[x * 4 + 1] = 20; r[x * 4 + 2] = 30; r[x * 4 + 3] = 255; } }
    id<MTLTexture> bt = [buf newTextureWithDescriptor:td offset:0 bytesPerRow:bpr];
    if (!bt) [bad appendString:@" buffer texture: nil"]; else view_check(bt, bad, "buffer");
    CFRelease(s);
    report(name, bad.length ? FAIL : PASS, bad.length ? bad : @"IOSurface and buffer textures, BGRA8 viewed as RGBA8");
}

// ---- 6. a kernel writes an sRGB texture: the values land, encoded ------------------------------------------------------
static void test_srgb_write(void)
{
    const char *name = "srgb-write";
    if (!wanted(name)) return;
    id<MTLComputePipelineState> p = cps(@"write_srgb");
    MTLTextureDescriptor *td = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm_sRGB width:16 height:16 mipmapped:NO];
    td.usage = MTLTextureUsageShaderWrite | MTLTextureUsageShaderRead;
    id<MTLTexture> t = [D newTextureWithDescriptor:td];
    if (!p || !t) { report(name, SKIP, @"no sRGB texture with ShaderWrite"); return; }
    id<MTLCommandBuffer> cb = [Q commandBuffer]; id<MTLComputeCommandEncoder> e = [cb computeCommandEncoder];
    [e setComputePipelineState:p]; [e setTexture:t atIndex:0]; [e dispatchThreads:MTLSizeMake(16, 16, 1) threadsPerThreadgroup:MTLSizeMake(8, 8, 1)]; [e endEncoding];
    id<MTLBlitCommandEncoder> bl = [cb blitCommandEncoder]; [bl synchronizeResource:t]; [bl endEncoding];
    [cb commit]; [cb waitUntilCompleted];
    uint8_t px[16 * 16 * 4]; [t getBytes:px bytesPerRow:64 fromRegion:MTLRegionMake2D(0, 0, 16, 16) mipmapLevel:0];
    // sRGB(0.5) = 188, sRGB(0.25) = 137, 1.0 = 255
    const BOOL ok = abs(px[0] - 188) <= 2 && abs(px[1] - 137) <= 2 && px[2] >= 253 && abs(px[1020] - 188) <= 2;
    report(name, ok ? PASS : FAIL, [NSString stringWithFormat:@"read %u,%u,%u,%u (want 188,137,255,255)", px[0], px[1], px[2], px[3]]);
}

// ---- 7. CoreImage on the GPU against CoreImage's software renderer -------------------------------------------------------
static int compare_rgba(const uint8_t *a, const uint8_t *b, int w, int h, double *mean, int *p999, BOOL flipB)
{
    long long sum = 0; int hist[256] = { 0 };
    for (int y = 0; y < h; y++) for (int x = 0; x < w; x++) {
        const uint8_t *pa = a + (y * w + x) * 4, *pb = b + ((flipB ? h - 1 - y : y) * w + x) * 4;
        int m = 0; for (int c = 0; c < 3; c++) { int d = abs(pa[c] - pb[c]); sum += d; if (d > m) m = d; }
        hist[m]++;
    }
    *mean = (double)sum / (w * h * 3);
    long long acc = 0, lim = (long long)w * h * 999 / 1000; *p999 = 255;
    for (int i = 0; i < 256; i++) { acc += hist[i]; if (acc >= lim) { *p999 = i; break; } }
    return 0;
}
static void test_coreimage(void)
{
    const char *name = "coreimage-gpu-vs-cpu";
    if (!wanted(name)) return;
    const int W = 512, H = 384;
    CGColorSpaceRef cs = CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
    uint8_t *src = malloc(W * H * 4);
    for (int y = 0; y < H; y++) for (int x = 0; x < W; x++) {
        uint8_t *p = src + (y * W + x) * 4;
        p[0] = (uint8_t)(x * 255 / W); p[1] = (uint8_t)(y * 255 / H); p[2] = ((x / 32 + y / 32) & 1) ? 230 : 40; p[3] = 255;
        if (x < 120 && y < 60) { p[0] = 255; p[1] = 220; p[2] = 0; }   // a yellow block top-left: shows a flipped result
    }
    NSData *data = [NSData dataWithBytesNoCopy:src length:W * H * 4 freeWhenDone:YES];
    CIImage *in = [CIImage imageWithBitmapData:data bytesPerRow:W * 4 size:CGSizeMake(W, H) format:kCIFormatRGBA8 colorSpace:cs];
    CIImage *img = [in imageByApplyingGaussianBlurWithSigma:2.5];
    img = [img imageByApplyingFilter:@"CIColorControls" withInputParameters:@{ kCIInputSaturationKey: @1.4, kCIInputContrastKey: @1.15 }];
    img = [img imageByApplyingTransform:CGAffineTransformMakeRotation(0.15)];
    img = [[img imageByCompositingOverImage:[CIImage imageWithColor:[CIColor colorWithRed:0.1 green:0.2 blue:0.3]]] imageByCroppingToRect:CGRectMake(0, 0, W, H)];
    CIContext *gpu = [CIContext contextWithMTLDevice:D options:@{ kCIContextWorkingColorSpace: (__bridge id)cs, kCIContextOutputColorSpace: (__bridge id)cs }];
    CIContext *cpu = [CIContext contextWithOptions:@{ kCIContextUseSoftwareRenderer: @YES, kCIContextWorkingColorSpace: (__bridge id)cs, kCIContextOutputColorSpace: (__bridge id)cs }];
    uint8_t *a = calloc(W * H, 4), *b = calloc(W * H, 4);
    [gpu render:img toBitmap:a rowBytes:W * 4 bounds:CGRectMake(0, 0, W, H) format:kCIFormatRGBA8 colorSpace:cs];
    [cpu render:img toBitmap:b rowBytes:W * 4 bounds:CGRectMake(0, 0, W, H) format:kCIFormatRGBA8 colorSpace:cs];
    double mean = 0, meanF = 0; int p999 = 0, p999F = 0;
    compare_rgba(a, b, W, H, &mean, &p999, NO); compare_rgba(a, b, W, H, &meanF, &p999F, YES);
    const BOOL ok = mean < 2.5 && p999 < 24;
    if (!ok) { save_png("coreimage-gpu", a, W, H, W * 4); save_png("coreimage-cpu", b, W, H, W * 4); }
    report(name, ok ? PASS : FAIL, [NSString stringWithFormat:@"mean difference %.2f, 99.9%% within %d%s", mean, p999,
                                    (!ok && meanF < mean / 3) ? " - the GPU image is upside down" : ""]);
    free(a); free(b); CGColorSpaceRelease(cs);
}

// ---- 8. OpenGL through the Metal driver against Apple's software OpenGL -------------------------------------------------
static BOOL gl_draw(BOOL accelerated, uint8_t *out, int W, int H, char *renderer, size_t rn)
{
    CGLPixelFormatAttribute hw[] = { kCGLPFAAccelerated, kCGLPFANoRecovery, kCGLPFAColorSize, (CGLPixelFormatAttribute)24, kCGLPFAAlphaSize, (CGLPixelFormatAttribute)8, (CGLPixelFormatAttribute)0 };
    CGLPixelFormatAttribute sw[] = { kCGLPFARendererID, (CGLPixelFormatAttribute)kCGLRendererGenericFloatID, kCGLPFAColorSize, (CGLPixelFormatAttribute)24, kCGLPFAAlphaSize, (CGLPixelFormatAttribute)8, (CGLPixelFormatAttribute)0 };
    CGLPixelFormatObj pf = NULL; GLint npf = 0;
    if (CGLChoosePixelFormat(accelerated ? hw : sw, &pf, &npf) != kCGLNoError || !pf) return NO;
    CGLContextObj ctx = NULL;
    CGLCreateContext(pf, NULL, &ctx); CGLDestroyPixelFormat(pf);
    if (!ctx) return NO;
    CGLSetCurrentContext(ctx);
    snprintf(renderer, rn, "%s", (const char *)glGetString(GL_RENDERER));
    GLuint fb = 0, rb = 0;
    glGenFramebuffersEXT(1, &fb); glBindFramebufferEXT(GL_FRAMEBUFFER_EXT, fb);
    glGenRenderbuffersEXT(1, &rb); glBindRenderbufferEXT(GL_RENDERBUFFER_EXT, rb);
    glRenderbufferStorageEXT(GL_RENDERBUFFER_EXT, GL_RGBA8, W, H);
    glFramebufferRenderbufferEXT(GL_FRAMEBUFFER_EXT, GL_COLOR_ATTACHMENT0_EXT, GL_RENDERBUFFER_EXT, rb);
    BOOL ok = glCheckFramebufferStatusEXT(GL_FRAMEBUFFER_EXT) == GL_FRAMEBUFFER_COMPLETE_EXT;
    if (ok) {
        glViewport(0, 0, W, H);
        glClearColor(0.0f, 0.0f, 0.25f, 1.0f); glClear(GL_COLOR_BUFFER_BIT);
        glMatrixMode(GL_PROJECTION); glLoadIdentity(); glOrtho(0, W, 0, H, -1, 1);
        glMatrixMode(GL_MODELVIEW); glLoadIdentity();
        // a gradient across the middle, as two triangles: a quad with four colours is split along whichever diagonal the
        // implementation picks (Apple's software renderer and Mesa pick different ones), and v63 failed on that alone
        glBegin(GL_TRIANGLES);
        glColor3f(1, 0, 0); glVertex2f(0, H * 0.3f); glColor3f(0, 1, 0); glVertex2f(W, H * 0.3f); glColor3f(0, 0, 1); glVertex2f(W, H * 0.6f);
        glColor3f(1, 0, 0); glVertex2f(0, H * 0.3f); glColor3f(0, 0, 1); glVertex2f(W, H * 0.6f); glColor3f(1, 1, 1); glVertex2f(0, H * 0.6f);
        glEnd();
        glColor3f(1, 1, 0); glBegin(GL_TRIANGLES); glVertex2f(8, 8); glVertex2f(60, 8); glVertex2f(8, 40); glEnd();   // yellow, bottom left
        glColor3f(0, 1, 1); glBegin(GL_QUADS); glVertex2f(W - 50, H - 30); glVertex2f(W - 6, H - 30); glVertex2f(W - 6, H - 6); glVertex2f(W - 50, H - 6); glEnd();
        glFinish();
        glReadPixels(0, 0, W, H, GL_RGBA, GL_UNSIGNED_BYTE, out);   // rows bottom to top in both contexts
    }
    glDeleteFramebuffersEXT(1, &fb); glDeleteRenderbuffersEXT(1, &rb);
    CGLSetCurrentContext(NULL); CGLDestroyContext(ctx);
    return ok;
}
static void test_opengl(void)
{
    const char *name = "opengl-vs-software";
    if (!wanted(name)) return;
    const int W = 256, H = 128;
    uint8_t *a = calloc(W * H, 4), *b = calloc(W * H, 4);
    char ra[128] = "", rb[128] = "";
    const BOOL ha = gl_draw(YES, a, W, H, ra, sizeof ra), hb = gl_draw(NO, b, W, H, rb, sizeof rb);
    if (!ha || !hb) { report(name, ha ? SKIP : FAIL, [NSString stringWithFormat:@"accelerated %s (%s), software %s", ha ? "ok" : "FAILED", ra, hb ? "ok" : "unavailable"]); free(a); free(b); return; }
    unsigned off = 0, offF = 0;
    for (int y = 0; y < H; y++) for (int x = 0; x < W; x++) {
        const uint8_t *pa = a + (y * W + x) * 4, *pb = b + (y * W + x) * 4, *pf = b + ((H - 1 - y) * W + x) * 4;
        int m = 0, mf = 0; for (int c = 0; c < 3; c++) { m = MAX(m, abs(pa[c] - pb[c])); mf = MAX(mf, abs(pa[c] - pf[c])); }
        if (m > 24) off++; if (mf > 24) offF++;
    }
    const BOOL ok = off < (unsigned)(W * H / 100);
    if (!ok) { save_png("opengl-accelerated", a, W, H, W * 4); save_png("opengl-software", b, W, H, W * 4); }
    report(name, ok ? PASS : FAIL, [NSString stringWithFormat:@"%u of %d pixels differ (%s vs %s)%s", off, W * H, ra, rb,
                                    (!ok && offF < off / 4) ? " - the accelerated image is upside down" : ""]);
    free(a); free(b);
}

// ---- 8b. Photo Booth's way to the screen, upside down on this driver (v71: where does it turn over?) --------------------
// An IOSurface whose first rows (the top of the picture) are red and the rest blue.
static IOSurfaceRef surface_red_top(int W, int H)
{
    NSDictionary *pr = @{ (id)kIOSurfaceWidth: @(W), (id)kIOSurfaceHeight: @(H), (id)kIOSurfaceBytesPerElement: @4,
                          (id)kIOSurfacePixelFormat: @((unsigned)'BGRA') };
    IOSurfaceRef s = IOSurfaceCreate((__bridge CFDictionaryRef)pr);
    if (!s) return NULL;
    IOSurfaceLock(s, 0, NULL);
    uint8_t *base = IOSurfaceGetBaseAddress(s); const size_t row = IOSurfaceGetBytesPerRow(s);
    for (int y = 0; y < H; y++) for (int x = 0; x < W; x++) {
        uint8_t *q = base + y * row + x * 4;   // BGRA
        q[0] = y < H / 2 ? 0 : 255; q[1] = 0; q[2] = y < H / 2 ? 255 : 0; q[3] = 255;
    }
    IOSurfaceUnlock(s, 0, NULL);
    return s;
}
// 'R', 'B' or '?' for an RGBA pixel
static char rb_of(const uint8_t *p) { return p[0] > 160 && p[2] < 90 ? 'R' : p[2] > 160 && p[0] < 90 ? 'B' : '?'; }
static CGLContextObj gl_context(BOOL accelerated)
{
    CGLPixelFormatAttribute hw[] = { kCGLPFAAccelerated, kCGLPFANoRecovery, kCGLPFAColorSize, (CGLPixelFormatAttribute)24, kCGLPFAAlphaSize, (CGLPixelFormatAttribute)8, (CGLPixelFormatAttribute)0 };
    CGLPixelFormatAttribute sw[] = { kCGLPFARendererID, (CGLPixelFormatAttribute)kCGLRendererGenericFloatID, kCGLPFAColorSize, (CGLPixelFormatAttribute)24, kCGLPFAAlphaSize, (CGLPixelFormatAttribute)8, (CGLPixelFormatAttribute)0 };
    CGLPixelFormatObj pf = NULL; GLint npf = 0; CGLContextObj ctx = NULL;
    if (CGLChoosePixelFormat(accelerated ? hw : sw, &pf, &npf) != kCGLNoError || !pf) return NULL;
    CGLCreateContext(pf, NULL, &ctx); CGLDestroyPixelFormat(pf);
    return ctx;
}
// an RGBA8 framebuffer object of W x H bound in the current context; 0 when incomplete
static GLuint gl_fbo(int W, int H, GLuint *rb)
{
    GLuint fb = 0;
    glGenFramebuffersEXT(1, &fb); glBindFramebufferEXT(GL_FRAMEBUFFER_EXT, fb);
    glGenRenderbuffersEXT(1, rb); glBindRenderbufferEXT(GL_RENDERBUFFER_EXT, *rb);
    glRenderbufferStorageEXT(GL_RENDERBUFFER_EXT, GL_RGBA8, W, H);
    glFramebufferRenderbufferEXT(GL_FRAMEBUFFER_EXT, GL_COLOR_ATTACHMENT0_EXT, GL_RENDERBUFFER_EXT, *rb);
    if (glCheckFramebufferStatusEXT(GL_FRAMEBUFFER_EXT) != GL_FRAMEBUFFER_COMPLETE_EXT) { glDeleteFramebuffersEXT(1, &fb); glDeleteRenderbuffersEXT(1, rb); return 0; }
    glViewport(0, 0, W, H);
    return fb;
}
// v72: a column of the framebuffer, bottom to top, as letters: R red, B blue, G green (the clear colour), K black,
// W white, ? anything else (the first one's value goes into odd)
static char px_class(const uint8_t *p)
{
    if (p[0] > 160 && p[1] < 90 && p[2] < 90) return 'R';
    if (p[2] > 160 && p[0] < 90 && p[1] < 90) return 'B';
    if (p[1] > 160 && p[0] < 90 && p[2] < 90) return 'G';
    if (p[0] < 40 && p[1] < 40 && p[2] < 40) return 'K';
    if (p[0] > 215 && p[1] > 215 && p[2] > 215) return 'W';
    return '?';
}
static void gl_column(int W, int H, char prof[9], char *odd, size_t on)
{
    uint8_t *fbuf = malloc((size_t)W * H * 4);
    glReadPixels(0, 0, W, H, GL_RGBA, GL_UNSIGNED_BYTE, fbuf);   // rows bottom to top
    if (odd && on) odd[0] = 0;
    for (int k = 0; k < 8; k++) {
        const uint8_t *q = fbuf + ((size_t)((2 * k + 1) * H / 16) * W + W / 2) * 4;
        prof[k] = px_class(q);
        if (prof[k] == '?' && odd && on && !odd[0]) snprintf(odd, on, " (first odd pixel %u,%u,%u,%u)", q[0], q[1], q[2], q[3]);
    }
    prof[8] = 0;
    free(fbuf);
}
// How a picture with red first rows (the top of the picture) reaches an OpenGL framebuffer, texel (0, 0) drawn at the
// framebuffer's (0, 0). OpenGL takes the first row as t = 0 (CoreVideo calls such textures flipped), so read bottom to top
// the column should be RRRRBBBB. The ways:
//   0 the IOSurface as a rectangle texture (CGLTexImageIOSurface2D, as CoreVideo's texture cache makes them), fixed function
//   1 the same bytes uploaded into a rectangle texture (glTexImage2D), fixed function
//   2 the same bytes in a 2D texture, normalized coordinates, fixed function
//   3 the IOSurface rectangle texture drawn by a GLSL shader (texture2DRect, as Core Image and Quartz Composer draw)
static const char *const kGLWays[4] = { "IOSurface rectangle", "rectangle from memory", "2D from memory", "IOSurface rectangle, GLSL" };
// v73: the texel a framebuffer point shows, out of a coordinate picture (R = 2x, G = 2y, B = 128; surface_coords):
// "fb(x,y)>(tx,ty)" for a 3x3 grid, x/y in OpenGL's framebuffer (from the bottom), tx/ty in the picture's memory
// (from its first row); "?" where the pixel is not one of the picture's
static void gl_grid(int W, int H, char *grid, size_t gn, int pts[9][2])
{
    uint8_t *fbuf = malloc((size_t)W * H * 4);
    glReadPixels(0, 0, W, H, GL_RGBA, GL_UNSIGNED_BYTE, fbuf);
    size_t used = 0; grid[0] = 0;
    const int xs[3] = { W / 8, W / 2, W - W / 8 - 1 }, ys[3] = { H / 8, H / 2, H - H / 8 - 1 };
    for (int j = 0; j < 3; j++) for (int i = 0; i < 3; i++) {
        const uint8_t *q = fbuf + ((size_t)ys[j] * W + xs[i]) * 4;
        int n;
        if (pts) { const int k = j * 3 + i, odd = abs(q[2] - 128) > 6; pts[k][0] = odd ? -1 : (q[0] + 1) / 2; pts[k][1] = odd ? -1 : (q[1] + 1) / 2; }
        if (abs(q[2] - 128) > 6) n = snprintf(grid + used, gn - used, " (%d,%d)>?%u,%u,%u", xs[i], ys[j], q[0], q[1], q[2]);
        else n = snprintf(grid + used, gn - used, " (%d,%d)>(%d,%d)", xs[i], ys[j], (q[0] + 1) / 2, (q[1] + 1) / 2);
        if (n < 0 || (size_t)n >= gn - used) break;
        used += (size_t)n;
    }
    free(fbuf);
}
static IOSurfaceRef surface_coords(int W, int H)
{
    NSDictionary *pr = @{ (id)kIOSurfaceWidth: @(W), (id)kIOSurfaceHeight: @(H), (id)kIOSurfaceBytesPerElement: @4,
                          (id)kIOSurfacePixelFormat: @((unsigned)'BGRA') };
    IOSurfaceRef s = IOSurfaceCreate((__bridge CFDictionaryRef)pr);
    if (!s) return NULL;
    IOSurfaceLock(s, 0, NULL);
    uint8_t *base = IOSurfaceGetBaseAddress(s); const size_t row = IOSurfaceGetBytesPerRow(s);
    for (int y = 0; y < H; y++) for (int x = 0; x < W; x++) {
        uint8_t *q = base + y * row + x * 4;   // BGRA
        q[0] = 128; q[1] = (uint8_t)(2 * y); q[2] = (uint8_t)(2 * x); q[3] = 255;
    }
    IOSurfaceUnlock(s, 0, NULL);
    return s;
}
static char *g_gl_grid; static size_t g_gl_grid_n;   // set: gl_texture_way fills it (nearest filtering)
static int gl_texture_way(BOOL accelerated, int way, IOSurfaceRef s, int W, int H, char prof[9], int *texH, char *odd, size_t on, char *renderer, size_t rn)
{
    CGLContextObj ctx = gl_context(accelerated);
    if (!ctx) return -1;
    CGLSetCurrentContext(ctx);
    snprintf(renderer, rn, "%s", (const char *)glGetString(GL_RENDERER));
    GLuint rb = 0, fb = gl_fbo(W, H, &rb), tex = 0, prog = 0;
    int r = -2;
    const GLenum target = way == 2 ? GL_TEXTURE_2D : GL_TEXTURE_RECTANGLE_ARB;
    if (fb) {
        glGenTextures(1, &tex); glBindTexture(target, tex);
        BOOL ok;
        if (way == 0 || way == 3) {
            ok = CGLTexImageIOSurface2D(ctx, target, GL_RGBA, W, H, GL_BGRA, GL_UNSIGNED_INT_8_8_8_8_REV, s, 0) == kCGLNoError;
            if (g_gl_grid) { glTexParameteri(target, GL_TEXTURE_MIN_FILTER, GL_NEAREST); glTexParameteri(target, GL_TEXTURE_MAG_FILTER, GL_NEAREST); }
        }
        else {
            IOSurfaceLock(s, kIOSurfaceLockReadOnly, NULL);
            glPixelStorei(GL_UNPACK_ROW_LENGTH, (GLint)(IOSurfaceGetBytesPerRow(s) / 4));
            glTexImage2D(target, 0, GL_RGBA8, W, H, 0, GL_BGRA, GL_UNSIGNED_INT_8_8_8_8_REV, IOSurfaceGetBaseAddress(s));
            glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
            IOSurfaceUnlock(s, kIOSurfaceLockReadOnly, NULL);
            glTexParameteri(target, GL_TEXTURE_MIN_FILTER, GL_NEAREST); glTexParameteri(target, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
            ok = glGetError() == GL_NO_ERROR;
        }
        GLint th = -1; glGetTexLevelParameteriv(target, 0, GL_TEXTURE_HEIGHT, &th); *texH = th;
        if (ok && way == 3) {
            const char *vs = "void main() { gl_TexCoord[0] = gl_MultiTexCoord0; gl_Position = ftransform(); }\n";
            const char *fs = "#extension GL_ARB_texture_rectangle : require\nuniform sampler2DRect t;\n"
                             "void main() { gl_FragColor = texture2DRect(t, gl_TexCoord[0].st); }\n";
            GLuint v = glCreateShader(GL_VERTEX_SHADER), f = glCreateShader(GL_FRAGMENT_SHADER);
            glShaderSource(v, 1, &vs, NULL); glCompileShader(v); glShaderSource(f, 1, &fs, NULL); glCompileShader(f);
            prog = glCreateProgram(); glAttachShader(prog, v); glAttachShader(prog, f); glLinkProgram(prog);
            GLint linked = 0; glGetProgramiv(prog, GL_LINK_STATUS, &linked);
            glDeleteShader(v); glDeleteShader(f);
            if (!linked) { ok = NO; r = -4; }
            else { glUseProgram(prog); glUniform1i(glGetUniformLocation(prog, "t"), 0); }
        }
        if (ok) {
            const float tw = way == 2 ? 1.0f : (float)W, tt = way == 2 ? 1.0f : (float)H;
            glClearColor(0, 1, 0, 1); glClear(GL_COLOR_BUFFER_BIT);
            glMatrixMode(GL_PROJECTION); glLoadIdentity(); glOrtho(0, W, 0, H, -1, 1);
            glMatrixMode(GL_MODELVIEW); glLoadIdentity();
            if (way != 3) { glEnable(target); glTexEnvi(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_REPLACE); }
            glBegin(GL_QUADS);
            glTexCoord2f(0, 0); glVertex2f(0, 0); glTexCoord2f(tw, 0); glVertex2f(W, 0);
            glTexCoord2f(tw, tt); glVertex2f(W, H); glTexCoord2f(0, tt); glVertex2f(0, H);
            glEnd();
            if (way != 3) glDisable(target); else glUseProgram(0);
            glFinish();
            gl_column(W, H, prof, odd, on);
            if (g_gl_grid) gl_grid(W, H, g_gl_grid, g_gl_grid_n, NULL);
            r = 0;
        } else if (r == -2) r = -3;
        if (prog) glDeleteProgram(prog);
        glDeleteTextures(1, &tex); glDeleteFramebuffersEXT(1, &fb); glDeleteRenderbuffersEXT(1, &rb);
    }
    CGLSetCurrentContext(NULL); CGLDestroyContext(ctx);
    return r;
}
static void test_gl_texture_ways(void)
{
    static const char *const names[4] = { "opengl-iosurface-texture", "opengl-rect-texture", "opengl-2d-texture", "opengl-iosurface-glsl" };
    const int W = 128, H = 96;
    for (int way = 0; way < 4; way++) {
        const char *name = names[way];
        if (!wanted(name)) continue;
        IOSurfaceRef s = surface_red_top(W, H);
        if (!s) { report(name, FAIL, @"no IOSurface"); continue; }
        char pa[9] = "", ps[9] = "", oa[64] = "", os[64] = "", ra[128] = "", rs[128] = "";
        int ha_h = -1, hs_h = -1;
        const int ha = gl_texture_way(YES, way, s, W, H, pa, &ha_h, oa, sizeof oa, ra, sizeof ra);
        const int hs = gl_texture_way(NO, way, s, W, H, ps, &hs_h, os, sizeof os, rs, sizeof rs);
        CFRelease(s);
        if (ha) { report(name, FAIL, [NSString stringWithFormat:@"%s: accelerated OpenGL could not draw it (%d, %s)", kGLWays[way], ha, ra]); continue; }
        const BOOL ok = !strcmp(pa, "RRRRBBBB");
        NSString *soft = hs ? [NSString stringWithFormat:@"could not draw it (%d)", hs] : [NSString stringWithFormat:@"%s%s", ps, os];
        report(name, ok ? PASS : FAIL, [NSString stringWithFormat:@"%s: column bottom to top %s%s (want RRRRBBBB), texture height %d, on %s; "
                                        "software OpenGL %@", kGLWays[way], pa, oa, ha_h, ra, soft]);
    }
}
// v73: which texel each framebuffer point shows, the four ways: the accelerated grid next to Apple's software OpenGL
static void test_gl_coord_map(void)
{
    static const char *const names[4] = { "opengl-map-iosurface-rect", "opengl-map-rect", "opengl-map-2d", "opengl-map-iosurface-glsl" };
    const int W = 128, H = 96;
    for (int way = 0; way < 4; way++) {
        const char *name = names[way];
        if (!wanted(name)) continue;
        IOSurfaceRef s = surface_coords(W, H);
        if (!s) { report(name, FAIL, @"no IOSurface"); continue; }
        char pa[9], ps[9], oa[64], os[64], ra[128], rs[128], ga[400], gs[400];
        int th = -1;
        g_gl_grid = ga; g_gl_grid_n = sizeof ga; ga[0] = 0;
        const int ha = gl_texture_way(YES, way, s, W, H, pa, &th, oa, sizeof oa, ra, sizeof ra);
        g_gl_grid = gs; g_gl_grid_n = sizeof gs; gs[0] = 0;
        const int hs = gl_texture_way(NO, way, s, W, H, ps, &th, os, sizeof os, rs, sizeof rs);
        g_gl_grid = NULL;
        CFRelease(s);
        if (ha) { report(name, FAIL, [NSString stringWithFormat:@"%s: accelerated OpenGL could not draw it (%d)", kGLWays[way], ha]); continue; }
        const BOOL ok = !hs && !strcmp(ga, gs);
        report(name, ok ? PASS : FAIL, [NSString stringWithFormat:@"%s: fb(x,y)>texel(x,y):%s | software:%s", kGLWays[way], ga, hs ? " (could not draw)" : gs]);
    }
}

// Core Image drawing into an IOSurface on the GPU (Metal) and on the CPU: the same rows should come out on top
static void test_coreimage_surface(void)
{
    const char *name = "coreimage-into-iosurface";
    if (!wanted(name)) return;
    const int W = 128, H = 96;
    IOSurfaceRef src = surface_red_top(W, H);
    IOSurfaceRef ga = surface_red_top(W, H), gb = surface_red_top(W, H);
    if (!src || !ga || !gb) { report(name, FAIL, @"no IOSurface"); return; }
    CGColorSpaceRef cs = CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
    CIImage *img = [[CIImage imageWithIOSurface:src] imageByApplyingFilter:@"CIColorControls" withInputParameters:@{ kCIInputSaturationKey: @1.0 }];
    CIContext *gpu = [CIContext contextWithMTLDevice:D options:@{ kCIContextWorkingColorSpace: (__bridge id)cs, kCIContextOutputColorSpace: (__bridge id)cs }];
    CIContext *cpu = [CIContext contextWithOptions:@{ kCIContextUseSoftwareRenderer: @YES, kCIContextWorkingColorSpace: (__bridge id)cs, kCIContextOutputColorSpace: (__bridge id)cs }];
    // paint the targets green first, so a render that never lands shows
    IOSurfaceRef targets[2] = { ga, gb };
    for (int k = 0; k < 2; k++) {
        IOSurfaceRef t = targets[k];
        IOSurfaceLock(t, 0, NULL); uint8_t *b = IOSurfaceGetBaseAddress(t); const size_t row = IOSurfaceGetBytesPerRow(t);
        for (int y = 0; y < H; y++) for (int x = 0; x < W; x++) { uint8_t *q = b + y * row + x * 4; q[0] = 0; q[1] = 255; q[2] = 0; q[3] = 255; }
        IOSurfaceUnlock(t, 0, NULL);
    }
    [gpu render:img toIOSurface:ga bounds:CGRectMake(0, 0, W, H) colorSpace:cs];
    [cpu render:img toIOSurface:gb bounds:CGRectMake(0, 0, W, H) colorSpace:cs];
    char rows[2][2];
    IOSurfaceRef both[2] = { ga, gb };
    for (int k = 0; k < 2; k++) {
        IOSurfaceLock(both[k], kIOSurfaceLockReadOnly, NULL);
        const uint8_t *b = IOSurfaceGetBaseAddress(both[k]); const size_t row = IOSurfaceGetBytesPerRow(both[k]);
        for (int j = 0; j < 2; j++) {
            const uint8_t *q = b + (j ? H - 3 : 2) * row + (W / 2) * 4;   // BGRA
            const uint8_t rgba[4] = { q[2], q[1], q[0], q[3] };
            rows[k][j] = rb_of(rgba);
        }
        IOSurfaceUnlock(both[k], kIOSurfaceLockReadOnly, NULL);
    }
    const BOOL ok = rows[0][0] == rows[1][0] && rows[0][1] == rows[1][1] && rows[1][0] != '?';
    report(name, ok ? PASS : FAIL, [NSString stringWithFormat:@"first row / last row: GPU %c %c, CPU %c %c", rows[0][0], rows[0][1], rows[1][0], rows[1][1]]);
    CGColorSpaceRelease(cs); CFRelease(src); CFRelease(ga); CFRelease(gb);
}
// v73: Core Image on OpenGL with the coordinate picture: an upright draw shows the picture's first row at the top,
// so fb(x,y) should show texel (x, H-1-y)
static void test_coreimage_opengl_map(void)
{
    const char *name = "coreimage-on-opengl-map";
    if (!wanted(name)) return;
    const int W = 128, H = 96;
    IOSurfaceRef s = surface_coords(W, H);
    CGLContextObj ctx = gl_context(YES);
    if (!s || !ctx) { report(name, SKIP, @"no IOSurface or no accelerated OpenGL"); if (s) CFRelease(s); if (ctx) CGLDestroyContext(ctx); return; }
    CGLSetCurrentContext(ctx);
    GLuint rb = 0, fb = gl_fbo(W, H, &rb);
    char grid[400] = "-";
    int pts[9][2]; memset(pts, 0xff, sizeof pts);
    if (fb) {
        glClearColor(0, 1, 0, 1); glClear(GL_COLOR_BUFFER_BIT);
        CGColorSpaceRef cs = CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
        CIContext *ci = [CIContext contextWithCGLContext:ctx pixelFormat:CGLGetPixelFormat(ctx) colorSpace:cs
                                                 options:@{ kCIContextWorkingColorSpace: [NSNull null] }];
        CIImage *img = [[CIImage imageWithIOSurface:s] imageBySamplingNearest];
        [ci drawImage:img inRect:CGRectMake(0, 0, W, H) fromRect:img.extent];
        glFinish();
        gl_grid(W, H, grid, sizeof grid, pts);
        CGColorSpaceRelease(cs);
        glDeleteFramebuffersEXT(1, &fb); glDeleteRenderbuffersEXT(1, &rb);
    }
    CGLSetCurrentContext(NULL); CGLDestroyContext(ctx); CFRelease(s);
    char want[400]; size_t used = 0; want[0] = 0;
    const int xs[3] = { W / 8, W / 2, W - W / 8 - 1 }, ys[3] = { H / 8, H / 2, H - H / 8 - 1 };
    int off = 0;
    for (int j = 0; j < 3; j++) for (int i = 0; i < 3; i++) {
        used += (size_t)snprintf(want + used, sizeof want - used, " (%d,%d)>(%d,%d)", xs[i], ys[j], xs[i], H - 1 - ys[j]);
        if (abs(pts[j * 3 + i][0] - xs[i]) > 1 || abs(pts[j * 3 + i][1] - (H - 1 - ys[j])) > 1) off++;
    }
    report(name, !off ? PASS : FAIL, [NSString stringWithFormat:@"fb(x,y)>texel(x,y):%s | upright:%s", grid, want]);
}

// Core Image on an OpenGL context drawing the picture into a framebuffer object, as an OpenGL app with Core Image
// effects shows a camera frame: upright, so the bottom row read back (OpenGL reads bottom up) is blue
static void test_coreimage_opengl(void)
{
    const char *name = "coreimage-on-opengl";
    if (!wanted(name)) return;
    const int W = 128, H = 96;
    IOSurfaceRef s = surface_red_top(W, H);
    CGLContextObj ctx = gl_context(YES);
    if (!s || !ctx) { report(name, SKIP, @"no IOSurface or no accelerated OpenGL"); if (s) CFRelease(s); if (ctx) CGLDestroyContext(ctx); return; }
    CGLSetCurrentContext(ctx);
    char renderer[128]; snprintf(renderer, sizeof renderer, "%s", (const char *)glGetString(GL_RENDERER));
    GLuint rb = 0, fb = gl_fbo(W, H, &rb);
    char bottom = '-', top = '-', prof[9] = "-", odd[64] = "";
    if (fb) {
        glClearColor(0, 1, 0, 1); glClear(GL_COLOR_BUFFER_BIT);
        CGColorSpaceRef cs = CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
        CIContext *ci = [CIContext contextWithCGLContext:ctx pixelFormat:CGLGetPixelFormat(ctx) colorSpace:cs options:nil];
        CIImage *img = [CIImage imageWithIOSurface:s];
        [ci drawImage:img inRect:CGRectMake(0, 0, W, H) fromRect:img.extent];
        glFinish();
        uint8_t px[4];
        glReadPixels(W / 2, 2, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, px); bottom = rb_of(px);
        glReadPixels(W / 2, H - 3, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, px); top = rb_of(px);
        gl_column(W, H, prof, odd, sizeof odd);
        CGColorSpaceRelease(cs);
        glDeleteFramebuffersEXT(1, &fb); glDeleteRenderbuffersEXT(1, &rb);
    }
    CGLSetCurrentContext(NULL); CGLDestroyContext(ctx); CFRelease(s);
    const BOOL ok = bottom == 'B' && top == 'R';
    report(name, ok ? PASS : FAIL, [NSString stringWithFormat:@"framebuffer bottom %c top %c (expected B R: upright), column bottom to top %s%s (upright BBBBRRRR) on %s%s",
                                    bottom, top, prof, odd, renderer, bottom == 'R' && top == 'B' ? " - upside down, as Photo Booth's preview" : ""]);
}

// ---- 8c. pixel-coordinate samplers, as OpenGL's rectangle textures reach Metal (v72) ------------------------------------
// A 32x32 picture whose texel (x, y) holds R = 8y, G = 8x, drawn into a 32x32 target where each fragment samples at its
// own pixel centre: every pixel should come back as its texel. Ordinary and IOSurface textures, nearest and linear, with
// the app's sampler (normalizedCoordinates NO) and with a constexpr coord::pixel one; and what get_width/get_height say.
static NSString *px_case(id<MTLTexture> src, id<MTLRenderPipelineState> rp, id<MTLSamplerState> smp, id<MTLComputePipelineState> rd)
{
    const int W = 32, H = 32;
    MTLTextureDescriptor *td = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm width:W height:H mipmapped:NO];
    td.usage = MTLTextureUsageRenderTarget | MTLTextureUsageShaderRead; td.storageMode = MTLStorageModePrivate;
    id<MTLTexture> t = [D newTextureWithDescriptor:td];
    id<MTLBuffer> out = [D newBufferWithLength:W * H * 4 options:MTLResourceStorageModeShared];
    id<MTLCommandBuffer> cb = [Q commandBuffer];
    MTLRenderPassDescriptor *rpd = [MTLRenderPassDescriptor renderPassDescriptor];
    rpd.colorAttachments[0].texture = t; rpd.colorAttachments[0].loadAction = MTLLoadActionClear; rpd.colorAttachments[0].storeAction = MTLStoreActionStore;
    rpd.colorAttachments[0].clearColor = MTLClearColorMake(0, 0, 1, 1);
    id<MTLRenderCommandEncoder> re = [cb renderCommandEncoderWithDescriptor:rpd];
    [re setRenderPipelineState:rp]; [re setFragmentTexture:src atIndex:0];
    if (smp) [re setFragmentSamplerState:smp atIndex:0];
    [re drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3]; [re endEncoding];
    id<MTLComputeCommandEncoder> ce = [cb computeCommandEncoder];
    [ce setComputePipelineState:rd]; [ce setTexture:t atIndex:0]; [ce setBuffer:out offset:0 atIndex:0];
    [ce dispatchThreads:MTLSizeMake(W, H, 1) threadsPerThreadgroup:MTLSizeMake(8, 8, 1)]; [ce endEncoding];
    [cb commit]; [cb waitUntilCompleted];
    const uint8_t *px = out.contents; int bad = 0;
    for (int y = 0; y < H; y++) for (int x = 0; x < W; x++) {
        const uint8_t *q = px + (y * W + x) * 4;
        if (abs(q[0] - 8 * y) > 2 || abs(q[1] - 8 * x) > 2) bad++;
    }
    if (!bad) return nil;
    NSMutableString *m = [NSMutableString stringWithFormat:@"%d of %d wrong, rows read at x=16 for y=0,4..28:", bad, W * H];
    for (int y = 0; y < H; y += 4) { const uint8_t *q = px + (y * W + 16) * 4; [m appendFormat:@" %.1f", q[0] / 8.0]; }
    const uint8_t *q = px + (16 * W + 16) * 4;
    [m appendFormat:@", column at (16,16) %.1f, pixel %u,%u,%u", q[1] / 8.0, q[0], q[1], q[2]];
    return m;
}
static void test_pixel_samplers(void)
{
    const char *name = "metal-pixel-sampler";
    if (!wanted(name)) return;
    const int W = 32, H = 32;
    id<MTLRenderPipelineState> app = rps(@"fs_tri", @"px_app", MTLPixelFormatRGBA8Unorm), own = rps(@"fs_tri", @"px_own", MTLPixelFormatRGBA8Unorm);
    id<MTLComputePipelineState> rd = cps(@"tex_to_buf"), sz = cps(@"tex_size");
    if (!app || !own || !rd || !sz) { report(name, FAIL, @"pipeline"); return; }
    IOSurfaceRef s = IOSurfaceCreate((__bridge CFDictionaryRef)@{ (id)kIOSurfaceWidth: @(W), (id)kIOSurfaceHeight: @(H), (id)kIOSurfaceBytesPerElement: @4,
                                                                  (id)kIOSurfacePixelFormat: @((uint32_t)'BGRA') });
    if (!s) { report(name, FAIL, @"no IOSurface"); return; }
    IOSurfaceLock(s, 0, NULL);
    for (int y = 0; y < H; y++) { uint8_t *r = (uint8_t *)IOSurfaceGetBaseAddress(s) + y * IOSurfaceGetBytesPerRow(s);
        for (int x = 0; x < W; x++) { r[x * 4] = 0x40; r[x * 4 + 1] = (uint8_t)(8 * x); r[x * 4 + 2] = (uint8_t)(8 * y); r[x * 4 + 3] = 255; } }
    IOSurfaceUnlock(s, 0, NULL);
    MTLTextureDescriptor *td = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatBGRA8Unorm width:W height:H mipmapped:NO];
    td.usage = MTLTextureUsageShaderRead; td.storageMode = MTLStorageModeShared;
    id<MTLTexture> st = [D newTextureWithDescriptor:td iosurface:s plane:0];
    td.storageMode = MTLStorageModeManaged;
    id<MTLTexture> ot = [D newTextureWithDescriptor:td];
    IOSurfaceLock(s, kIOSurfaceLockReadOnly, NULL);
    [ot replaceRegion:MTLRegionMake2D(0, 0, W, H) mipmapLevel:0 withBytes:IOSurfaceGetBaseAddress(s) bytesPerRow:IOSurfaceGetBytesPerRow(s)];
    IOSurfaceUnlock(s, kIOSurfaceLockReadOnly, NULL);
    if (!st || !ot) { report(name, FAIL, @"no texture"); CFRelease(s); return; }
    MTLSamplerDescriptor *sd = [MTLSamplerDescriptor new];
    sd.normalizedCoordinates = NO; sd.sAddressMode = sd.tAddressMode = MTLSamplerAddressModeClampToEdge;
    sd.minFilter = sd.magFilter = MTLSamplerMinMagFilterNearest;
    id<MTLSamplerState> nearest = [D newSamplerStateWithDescriptor:sd];
    sd.minFilter = sd.magFilter = MTLSamplerMinMagFilterLinear;
    id<MTLSamplerState> linear = [D newSamplerStateWithDescriptor:sd];
    NSMutableString *bad = [NSMutableString string];
    if (!nearest || !linear) [bad appendString:@" no pixel sampler state;"];
    const char *what[6] = { "texture, app sampler nearest", "texture, app sampler linear", "IOSurface, app sampler nearest",
                            "IOSurface, app sampler linear", "texture, coord::pixel", "IOSurface, coord::pixel" };
    id<MTLTexture> tex[6] = { ot, ot, st, st, ot, st };
    id<MTLSamplerState> smp[6] = { nearest, linear, nearest, linear, nil, nil };
    for (int i = 0; i < 6; i++) {
        if (i < 4 && !smp[i]) continue;
        NSString *m = px_case(tex[i], i < 4 ? app : own, smp[i], rd);
        if (m) [bad appendFormat:@" %s: %@;", what[i], m];
    }
    id<MTLBuffer> out = [D newBufferWithLength:16 options:MTLResourceStorageModeShared];
    uint32_t dims[2][2];
    id<MTLTexture> both[2] = { ot, st };
    for (int k = 0; k < 2; k++) {
        memset(out.contents, 0xff, 16);
        id<MTLCommandBuffer> cb = [Q commandBuffer]; id<MTLComputeCommandEncoder> e = [cb computeCommandEncoder];
        [e setComputePipelineState:sz]; [e setTexture:both[k] atIndex:0]; [e setBuffer:out offset:0 atIndex:0];
        [e dispatchThreads:MTLSizeMake(1, 1, 1) threadsPerThreadgroup:MTLSizeMake(1, 1, 1)]; [e endEncoding];
        [cb commit]; [cb waitUntilCompleted];
        memcpy(dims[k], out.contents, 8);
        if (dims[k][0] != (uint32_t)W || dims[k][1] != (uint32_t)H) [bad appendFormat:@" %s reports %ux%u;", k ? "IOSurface texture" : "texture", dims[k][0], dims[k][1]];
    }
    CFRelease(s);
    report(name, bad.length ? FAIL : PASS, bad.length ? bad : [NSString stringWithFormat:@"6 ways each texel at its pixel; sizes %ux%u and %ux%u",
                                                               dims[0][0], dims[0][1], dims[1][0], dims[1][1]]);
}

// ---- 9. VideoToolbox: encode frames, decode them, compare --------------------------------------------------------------
typedef struct { CFMutableArrayRef samples; OSStatus err; int count; } enc_ctx;
static void enc_out(void *ref, void *src, OSStatus st, VTEncodeInfoFlags fl, CMSampleBufferRef sb)
{
    enc_ctx *c = ref; if (st) c->err = st;
    if (sb) { CFArrayAppendValue(c->samples, sb); c->count++; }
}
typedef struct { CVPixelBufferRef last; OSStatus err; int count; } dec_ctx;
static void dec_out(void *ref, void *src, OSStatus st, VTDecodeInfoFlags fl, CVImageBufferRef img, CMTime pts, CMTime dur)
{
    dec_ctx *c = ref; if (st) c->err = st;
    if (img) { if (c->last) CVPixelBufferRelease(c->last); c->last = CVPixelBufferRetain(img); c->count++; }
}
static void fill_frame(CVPixelBufferRef pb, int f)
{
    CVPixelBufferLockBaseAddress(pb, 0);
    uint8_t *base = CVPixelBufferGetBaseAddress(pb); const size_t row = CVPixelBufferGetBytesPerRow(pb);
    const int W = (int)CVPixelBufferGetWidth(pb), H = (int)CVPixelBufferGetHeight(pb);
    for (int y = 0; y < H; y++) for (int x = 0; x < W; x++) {
        uint8_t *p = base + y * row + x * 4;   // BGRA: smooth gradients and a moving square
        p[0] = (uint8_t)(128 + 100 * sin((x + f * 6) / 40.0)); p[1] = (uint8_t)(y * 255 / H); p[2] = (uint8_t)(x * 255 / W); p[3] = 255;
        if (x >= 40 + f * 8 && x < 120 + f * 8 && y >= 100 && y < 180) { p[0] = 20; p[1] = 230; p[2] = 240; }
    }
    CVPixelBufferUnlockBaseAddress(pb, 0);
}
static double psnr_bgra(CVPixelBufferRef a, CVPixelBufferRef b)
{
    CVPixelBufferLockBaseAddress(a, kCVPixelBufferLock_ReadOnly); CVPixelBufferLockBaseAddress(b, kCVPixelBufferLock_ReadOnly);
    const int W = (int)CVPixelBufferGetWidth(a), H = (int)CVPixelBufferGetHeight(a);
    const uint8_t *pa = CVPixelBufferGetBaseAddress(a), *pb = CVPixelBufferGetBaseAddress(b);
    const size_t ra = CVPixelBufferGetBytesPerRow(a), rb = CVPixelBufferGetBytesPerRow(b);
    double se = 0;
    for (int y = 0; y < H; y++) for (int x = 0; x < W; x++) for (int c = 0; c < 3; c++) { double d = (double)pa[y * ra + x * 4 + c] - pb[y * rb + x * 4 + c]; se += d * d; }
    CVPixelBufferUnlockBaseAddress(a, kCVPixelBufferLock_ReadOnly); CVPixelBufferUnlockBaseAddress(b, kCVPixelBufferLock_ReadOnly);
    const double mse = se / (W * H * 3.0);
    return mse > 0 ? 10 * log10(255.0 * 255.0 / mse) : 99;
}
static void test_video(const char *name, CMVideoCodecType codec)
{
    if (!wanted(name)) return;
    enum { W = 640, H = 360, N = 30 };
    NSDictionary *spec = @{ (id)kVTVideoEncoderSpecification_EnableHardwareAcceleratedVideoEncoder: @YES };
    NSDictionary *pbattr = @{ (id)kCVPixelBufferPixelFormatTypeKey: @(kCVPixelFormatType_32BGRA), (id)kCVPixelBufferWidthKey: @(W), (id)kCVPixelBufferHeightKey: @(H),
                              (id)kCVPixelBufferIOSurfacePropertiesKey: @{} };
    enc_ctx ec = { CFArrayCreateMutable(NULL, 0, &kCFTypeArrayCallBacks), 0, 0 };
    VTCompressionSessionRef cs = NULL;
    OSStatus st = VTCompressionSessionCreate(NULL, W, H, codec, (__bridge CFDictionaryRef)spec, (__bridge CFDictionaryRef)pbattr, NULL, enc_out, &ec, &cs);
    if (st || !cs) { report(name, codec == kCMVideoCodecType_HEVC ? SKIP : FAIL, [NSString stringWithFormat:@"VTCompressionSessionCreate %d", (int)st]); CFRelease(ec.samples); return; }
    VTSessionSetProperty(cs, kVTCompressionPropertyKey_RealTime, kCFBooleanTrue);
    VTSessionSetProperty(cs, kVTCompressionPropertyKey_AverageBitRate, (__bridge CFTypeRef)@4000000);
    VTSessionSetProperty(cs, kVTCompressionPropertyKey_MaxKeyFrameInterval, (__bridge CFTypeRef)@30);
    CFBooleanRef hwFlag = NULL;
    VTSessionCopyProperty(cs, kVTCompressionPropertyKey_UsingHardwareAcceleratedVideoEncoder, NULL, &hwFlag);
    const BOOL hw = hwFlag == kCFBooleanTrue; if (hwFlag) CFRelease(hwFlag);
    CVPixelBufferRef frames[N] = { 0 };
    for (int f = 0; f < N; f++) {
        CVPixelBufferCreate(NULL, W, H, kCVPixelFormatType_32BGRA, (__bridge CFDictionaryRef)@{ (id)kCVPixelBufferIOSurfacePropertiesKey: @{} }, &frames[f]);
        fill_frame(frames[f], f);
        OSStatus e = VTCompressionSessionEncodeFrame(cs, frames[f], CMTimeMake(f, 30), CMTimeMake(1, 30), NULL, NULL, NULL);
        if (e) ec.err = e;
    }
    VTCompressionSessionCompleteFrames(cs, kCMTimeInvalid);
    VTCompressionSessionInvalidate(cs); CFRelease(cs);
    NSString *detail = nil; int result = PASS;
    if (ec.err || ec.count < N - 2) {
        result = FAIL; detail = [NSString stringWithFormat:@"encoder %s: %d of %d frames, status %d", hw ? "hardware" : "software", ec.count, N, (int)ec.err];
    } else {
        CMSampleBufferRef first = (CMSampleBufferRef)CFArrayGetValueAtIndex(ec.samples, 0);
        CMFormatDescriptionRef fd = CMSampleBufferGetFormatDescription(first);
        dec_ctx dc = { NULL, 0, 0 };
        VTDecompressionOutputCallbackRecord cb = { dec_out, &dc };
        VTDecompressionSessionRef ds = NULL;
        st = VTDecompressionSessionCreate(NULL, fd, NULL, (__bridge CFDictionaryRef)@{ (id)kCVPixelBufferPixelFormatTypeKey: @(kCVPixelFormatType_32BGRA) }, &cb, &ds);
        if (st || !ds) { result = FAIL; detail = [NSString stringWithFormat:@"encoded %d frames (%s); VTDecompressionSessionCreate %d", ec.count, hw ? "hardware" : "software", (int)st]; }
        else {
            for (CFIndex i = 0; i < CFArrayGetCount(ec.samples); i++) {
                OSStatus e = VTDecompressionSessionDecodeFrame(ds, (CMSampleBufferRef)CFArrayGetValueAtIndex(ec.samples, i), 0, NULL, NULL);
                if (e) dc.err = e;
            }
            VTDecompressionSessionWaitForAsynchronousFrames(ds);
            VTDecompressionSessionInvalidate(ds); CFRelease(ds);
            const double q = dc.last ? psnr_bgra(frames[N - 1], dc.last) : 0;
            if (dc.err || dc.count < ec.count - 2 || q < 28) result = FAIL;
            detail = [NSString stringWithFormat:@"encoder %s, %d frames encoded, %d decoded, last frame PSNR %.1f dB (want >= 28)%s",
                      hw ? "hardware" : "software", ec.count, dc.count, q, dc.err ? [NSString stringWithFormat:@", decode status %d", (int)dc.err].UTF8String : ""];
            if (dc.last) CVPixelBufferRelease(dc.last);
        }
    }
    for (int f = 0; f < N; f++) if (frames[f]) CVPixelBufferRelease(frames[f]);
    CFRelease(ec.samples);
    report(name, result, detail);
}

// ---- 10. VideoToolbox driven as WebRTC drives it (Telegram's tgcalls, Chromium): the encoder's output must mark its key
// frames as sync samples and carry the parameter sets, or the far end never gets a picture it can start decoding from.
// tgcalls: a frame is a key frame when its first sample attachment has no kCMSampleAttachmentKey_NotSync, and only key
// frames get the VPS/SPS/PPS (H.264: SPS/PPS) from the format description put in front of them.
typedef struct { CMVideoCodecType codec; int n, sync, noattach, firstSync, firstAttach, ps, hdr, forcedSync, rawFirst, rawSync; OSStatus err, psErr; char nals[64]; } kf_ctx;
// CoreMedia's own function, past any fix the Metal driver puts on this program's imports: what the encoder attached
static CFArrayRef (*kf_raw_attach)(CMSampleBufferRef, Boolean);
static void kf_note_nals(kf_ctx *c, CMSampleBufferRef sb)
{
    CMBlockBufferRef bb = CMSampleBufferGetDataBuffer(sb);
    const size_t len = bb ? CMBlockBufferGetDataLength(bb) : 0;
    size_t off = 0; int k = 0; c->nals[0] = 0;
    while (bb && c->hdr > 0 && c->hdr <= 4 && off + c->hdr < len && k < 8) {
        uint8_t h[5] = { 0 };
        if (CMBlockBufferCopyDataBytes(bb, off, c->hdr + 1, h)) break;
        uint32_t n = 0; for (int i = 0; i < c->hdr; i++) n = (n << 8) | h[i];
        const int type = c->codec == kCMVideoCodecType_HEVC ? (h[c->hdr] >> 1) & 0x3f : h[c->hdr] & 0x1f;
        const size_t used = strlen(c->nals);
        snprintf(c->nals + used, sizeof c->nals - used, "%s%d", k ? "," : "", type);
        off += c->hdr + n; k++;
    }
}
static void kf_out(void *ref, void *src, OSStatus st, VTEncodeInfoFlags fl, CMSampleBufferRef sb)
{
    kf_ctx *c = ref;
    if (st) { c->err = st; return; }
    if (!sb || (fl & kVTEncodeInfo_FrameDropped)) return;
    if (!kf_raw_attach) kf_raw_attach = (CFArrayRef (*)(CMSampleBufferRef, Boolean))dlsym(RTLD_DEFAULT, "CMSampleBufferGetSampleAttachmentsArray");
    CFArrayRef raw = kf_raw_attach ? kf_raw_attach(sb, false) : NULL;
    CFTypeRef rv = (raw && CFArrayGetCount(raw)) ? CFDictionaryGetValue((CFDictionaryRef)CFArrayGetValueAtIndex(raw, 0), kCMSampleAttachmentKey_NotSync) : NULL;
    const int rawState = !rv ? 0 : (CFGetTypeID(rv) == CFBooleanGetTypeID() && !CFBooleanGetValue((CFBooleanRef)rv)) ? 1 : 2;   // absent, false, true
    if (!c->n) c->rawFirst = rawState;
    if (rawState != 2) c->rawSync++;
    CFArrayRef at = CMSampleBufferGetSampleAttachmentsArray(sb, false);
    const BOOL attach = at && CFArrayGetCount(at);
    const BOOL sync = attach && !CFDictionaryContainsKey((CFDictionaryRef)CFArrayGetValueAtIndex(at, 0), kCMSampleAttachmentKey_NotSync);
    if (!attach) c->noattach++;
    if (sync) c->sync++;
    const int f = (int)(intptr_t)src;
    if (sync && (f == 0 || f == 30)) c->forcedSync++;
    if (!c->n) {
        c->firstSync = sync; c->firstAttach = attach;
        CMFormatDescriptionRef fd = CMSampleBufferGetFormatDescription(sb);
        size_t count = 0; int hdr = 0;
        c->psErr = c->codec == kCMVideoCodecType_HEVC ? CMVideoFormatDescriptionGetHEVCParameterSetAtIndex(fd, 0, NULL, NULL, &count, &hdr)
                                                       : CMVideoFormatDescriptionGetH264ParameterSetAtIndex(fd, 0, NULL, NULL, &count, &hdr);
        c->ps = (int)count; c->hdr = hdr;
        kf_note_nals(c, sb);
    }
    c->n++;
}
static void fill_nv12(CVPixelBufferRef pb, int f)
{
    CVPixelBufferLockBaseAddress(pb, 0);
    for (int p = 0; p < 2; p++) {
        uint8_t *b = CVPixelBufferGetBaseAddressOfPlane(pb, p); const size_t row = CVPixelBufferGetBytesPerRowOfPlane(pb, p);
        const int w = (int)CVPixelBufferGetWidthOfPlane(pb, p) * (p ? 2 : 1), h = (int)CVPixelBufferGetHeightOfPlane(pb, p);
        for (int y = 0; y < h; y++) for (int x = 0; x < w; x++) b[y * row + x] = (uint8_t)(p ? 128 + 40 * sin((x + f * 4) / 30.0) : 30 + ((x + y + f * 6) & 0xbf));
    }
    CVPixelBufferUnlockBaseAddress(pb, 0);
}
static void test_webrtc_keyframes(const char *name, CMVideoCodecType codec)
{
    if (!wanted(name)) return;
    enum { W = 1280, H = 720, N = 60 };
    NSDictionary *spec = @{ (id)kVTVideoEncoderSpecification_EnableHardwareAcceleratedVideoEncoder: @YES };
    NSDictionary *src = @{ (id)kCVPixelBufferOpenGLCompatibilityKey: @YES, (id)kCVPixelBufferIOSurfacePropertiesKey: @{},
                           (id)kCVPixelBufferPixelFormatTypeKey: @(kCVPixelFormatType_420YpCbCr8BiPlanarFullRange) };
    kf_ctx c = { .codec = codec };
    VTCompressionSessionRef cs = NULL;
    OSStatus st = VTCompressionSessionCreate(NULL, W, H, codec, (__bridge CFDictionaryRef)spec, (__bridge CFDictionaryRef)src, NULL, kf_out, &c, &cs);
    if (st || !cs) { report(name, codec == kCMVideoCodecType_HEVC ? SKIP : FAIL, [NSString stringWithFormat:@"VTCompressionSessionCreate %d", (int)st]); return; }
    VTSessionSetProperty(cs, kVTCompressionPropertyKey_RealTime, kCFBooleanFalse);
    VTSessionSetProperty(cs, kVTCompressionPropertyKey_AllowFrameReordering, kCFBooleanFalse);
    VTSessionSetProperty(cs, kVTCompressionPropertyKey_AverageBitRate, (__bridge CFTypeRef)@1000000);
    const OSStatus limits = VTSessionSetProperty(cs, kVTCompressionPropertyKey_DataRateLimits, (__bridge CFTypeRef)@[ @(1000000 * 1.5 / 8), @1 ]);
    VTSessionSetProperty(cs, kVTCompressionPropertyKey_MaxKeyFrameInterval, (__bridge CFTypeRef)@7200);
    VTSessionSetProperty(cs, kVTCompressionPropertyKey_MaxKeyFrameIntervalDuration, (__bridge CFTypeRef)@240);
    VTCompressionSessionPrepareToEncodeFrames(cs);
    CFBooleanRef hwFlag = NULL;
    VTSessionCopyProperty(cs, kVTCompressionPropertyKey_UsingHardwareAcceleratedVideoEncoder, NULL, &hwFlag);
    const BOOL hw = hwFlag == kCFBooleanTrue; if (hwFlag) CFRelease(hwFlag);
    CVPixelBufferPoolRef pool = VTCompressionSessionGetPixelBufferPool(cs);
    for (int f = 0; f < N; f++) {
        CVPixelBufferRef pb = NULL;
        if (pool) CVPixelBufferPoolCreatePixelBuffer(NULL, pool, &pb);
        if (!pb) CVPixelBufferCreate(NULL, W, H, kCVPixelFormatType_420YpCbCr8BiPlanarFullRange, (__bridge CFDictionaryRef)@{ (id)kCVPixelBufferIOSurfacePropertiesKey: @{} }, &pb);
        fill_nv12(pb, f);
        // a key frame at the start and one asked for later, as WebRTC does at the start of a call and on a far-end request
        NSDictionary *opt = (f == 0 || f == 30) ? @{ (id)kVTEncodeFrameOptionKey_ForceKeyFrame: @YES } : nil;
        OSStatus e = VTCompressionSessionEncodeFrame(cs, pb, CMTimeMake(f * 33, 1000), kCMTimeInvalid, (__bridge CFDictionaryRef)opt, (void *)(intptr_t)f, NULL);
        if (e) c.err = e;
        CVPixelBufferRelease(pb);
    }
    VTCompressionSessionCompleteFrames(cs, kCMTimeInvalid);
    VTCompressionSessionInvalidate(cs); CFRelease(cs);
    const int wantPs = codec == kCMVideoCodecType_HEVC ? 3 : 2;
    const BOOL ok = !c.err && c.n >= N - 2 && c.firstSync && c.forcedSync == 2 && c.ps >= wantPs;
    static const char *const rawName[] = { "no NotSync", "NotSync=false", "NotSync=true" };
    report(name, ok ? PASS : FAIL, [NSString stringWithFormat:@"encoder %s, %d frames; the encoder attached %s to the first frame (%d frame(s) without NotSync=true); "
                                    "as an application reads it: first frame %s; %d sync frame(s), %d of the 2 forced; %d without attachments; "
                                    "%d parameter set(s) in the format (status %d, want %d), NAL length %d; first frame NAL types %s; data rate limits %s%s",
                                    hw ? "hardware" : "software", c.n, rawName[c.rawFirst], c.rawSync, c.firstSync ? "SYNC" : (c.firstAttach ? "marked NotSync" : "has NO attachments"),
                                    c.sync, c.forcedSync, c.noattach, c.ps, (int)c.psErr, wantPs, c.hdr, c.nals[0] ? c.nals : "-",
                                    limits ? "refused" : "set", c.err ? [NSString stringWithFormat:@"; status %d", (int)c.err].UTF8String : ""]);
}

int main(int argc, char **argv)
{
    @autoreleasepool {
        g_argc = argc; g_argv = argv;
        D = MTLCreateSystemDefaultDevice();
        if (!D) { printf("TEST metal-device: FAIL no Metal device\n"); return 1; }
        Q = [D newCommandQueue];
        NSError *e = nil;
        L = [D newLibraryWithSource:kSrc options:nil error:&e];
        printf("device=%s macOS=%s\n", D.name.UTF8String, NSProcessInfo.processInfo.operatingSystemVersionString.UTF8String);
        if (!L) { printf("TEST metal-library: FAIL %s\n", e.description.UTF8String); return 1; }
        test_chain("compute-chain-serial", NO, NO);
        test_chain("compute-chain-serial-encoders", NO, YES);
        test_chain("compute-chain-concurrent", YES, NO);
        test_chain("compute-chain-concurrent-encoders", YES, YES);
        test_render_then_compute();
        test_sampler_park();
        test_mips();
        test_views();
        test_srgb_write();
        test_coreimage();
        test_opengl();
        test_gl_texture_ways();
        test_gl_coord_map();
        test_pixel_samplers();
        test_coreimage_surface();
        test_coreimage_opengl();
        test_coreimage_opengl_map();
        test_video("video-h264-roundtrip", kCMVideoCodecType_H264);
        test_video("video-hevc-roundtrip", kCMVideoCodecType_HEVC);
        test_webrtc_keyframes("video-h264-webrtc-keyframes", kCMVideoCodecType_H264);
        test_webrtc_keyframes("video-hevc-webrtc-keyframes", kCMVideoCodecType_HEVC);
        printf("SUMMARY: %d passed, %d failed, %d skipped\n", g_pass, g_fail, g_skip);
        return g_fail ? 1 : 0;
    }
}
