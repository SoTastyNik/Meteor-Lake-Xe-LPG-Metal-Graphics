#include <cassert>
#include "../NullMoth/kexts/NVRM/accel/nv_framebuffer_registration.h"
struct Framebuffer { int id; };
struct Pipe { Framebuffer *fb; };
int main() {
    Framebuffer target{1}, other{2}; Pipe a{&target}, b{&other};
    Pipe *pipes[kNvDisplayPipeSlots] = {};
    unsigned reads = 0;
    auto owner = [&](Pipe *p) { ++reads; return p->fb; };
    assert(nvFindFramebufferPipe(pipes, 0, &target, owner) == kNvPipeAbsent);
    pipes[0] = &a;
    assert(nvFindFramebufferPipe(pipes, 1, &target, owner) == 0);
    pipes[0] = &b;
    assert(nvFindFramebufferPipe(pipes, 1, &target, owner) == kNvPipeAbsent);
    pipes[1] = &a;
    assert(nvFindFramebufferPipe(pipes, 2, &target, owner) == 1);
    pipes[0] = &a;
    assert(nvFindFramebufferPipe(pipes, 2, &target, owner) == kNvPipeInvalid);
    pipes[0] = nullptr;
    assert(nvFindFramebufferPipe(pipes, 2, &target, owner) == kNvPipeInvalid);
    reads = 0;
    assert(nvFindFramebufferPipe(pipes, kNvDisplayPipeSlots + 1, &target, owner) == kNvPipeInvalid);
    assert(reads == 0);
    for (auto &p : pipes) p = &b;
    pipes[kNvDisplayPipeSlots - 1] = &a;
    assert(nvFindFramebufferPipe(pipes, kNvDisplayPipeSlots, &target, owner) == kNvDisplayPipeSlots - 1);
}
