#include <assert.h>
#include "../NullMoth/plugin/nvmtl_desktop_policy.h"
int main(void) {
    assert(nvmtl_desktop_stall_policy(0x8086,0x7d45,"WindowServer",NULL));
    assert(!nvmtl_desktop_stall_policy(0x8086,0x7d45,"latitude-metal-test",NULL));
    assert(!nvmtl_desktop_stall_policy(0x8086,0x7d55,"WindowServer",NULL));
    assert(!nvmtl_desktop_stall_policy(0x10de,0x7d45,"WindowServer",NULL));
    assert(!nvmtl_desktop_stall_policy(0x8086,0x7d45,"WindowServer",""));
    assert(!nvmtl_desktop_stall_policy(0x8086,0x7d45,"WindowServer","sync"));
    assert(!nvmtl_desktop_stall_policy(0x8086,0x7d45,NULL,NULL));
}
