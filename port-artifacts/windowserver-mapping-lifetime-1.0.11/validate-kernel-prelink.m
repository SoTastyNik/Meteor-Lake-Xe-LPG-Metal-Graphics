#import <Foundation/Foundation.h>
// kmutil may print several XML plists with headers and NUL padding.
// Validate one exact executable record, never a UUID belonging to another kext.
int main(int argc, const char **argv) { @autoreleasepool {
    if (argc != 5) { fprintf(stderr, "usage: validate-kernel-prelink dump expected-uuid permanent-bundle-path expected-version\n"); return 2; }
    NSData *input = [NSData dataWithContentsOfFile:@(argv[1])];
    NSUUID *expected = [[NSUUID alloc] initWithUUIDString:@(argv[2])];
    if (!input || !expected || input.length > 64*1024*1024) return 2;
    NSData *start = [@"<?xml" dataUsingEncoding:NSUTF8StringEncoding];
    NSData *end = [@"</plist>" dataUsingEncoding:NSUTF8StringEncoding];
    NSUInteger offset=0, found=0, collections=0;
    while (offset < input.length) {
        NSRange a=[input rangeOfData:start options:0 range:NSMakeRange(offset,input.length-offset)];
        if (a.location==NSNotFound) break;
        NSRange b=[input rangeOfData:end options:0 range:NSMakeRange(a.location,input.length-a.location)];
        if (b.location==NSNotFound) return 2;
        offset=NSMaxRange(b);
        id plist=[NSPropertyListSerialization propertyListWithData:[input subdataWithRange:NSMakeRange(a.location,offset-a.location)] options:NSPropertyListImmutable format:NULL error:NULL];
        if (![plist isKindOfClass:[NSDictionary class]]) return 2;
        id records=plist[@"_PrelinkInfoDictionary"];
        if (![records isKindOfClass:[NSArray class]]) return 2;
        collections++;
        for (id record in records) {
            if (![record isKindOfClass:[NSDictionary class]]) return 2;
            if (![record[@"CFBundleIdentifier"] isEqual:@"com.nullmoth.NMXGPU"]) continue;
            found++;
            id uuid=record[@"OSBundleUUID"];
            uuid_t bytes; [expected getUUIDBytes:bytes];
            if (![uuid isKindOfClass:[NSData class]] || ![uuid isEqualToData:[NSData dataWithBytes:bytes length:16]] ||
                ![record[@"_PrelinkBundlePath"] isEqual:@(argv[3])] ||
                ![record[@"_PrelinkExecutableRelativePath"] isEqual:@"Contents/MacOS/NMXGPU"] ||
                ![record[@"CFBundleVersion"] isEqual:@(argv[4])] ||
                ![record[@"_PrelinkExecutableSize"] isKindOfClass:[NSNumber class]] ||
                [record[@"_PrelinkExecutableSize"] unsignedLongLongValue]==0) {
                fprintf(stderr,"GPU collection record has incorrect identity, UUID, version, executable or path\n"); return 2;
            }
        }
    }
    if (!collections || found!=1) { fprintf(stderr,"Expected exactly one GPU collection record; found %lu\n",(unsigned long)found); return 2; }
    printf("Verified com.nullmoth.NMXGPU %s UUID=%s path=%s\n",argv[4],expected.UUIDString.UTF8String,argv[3]);
    return 0;
} }
