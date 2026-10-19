#include <assert.h>
#include "../NullMoth/plugin/nvmtl_log_failure.h"
int main(void) {
    assert(nvmtl_log_failure("vk: fence wait -> 2 after 5000 ms (budget 5000 ms); disabling backend without retiring in-flight resources"));
    assert(nvmtl_log_failure("vk: queue submit -> -4; disabling backend and retaining uncertain in-flight resources"));
    assert(nvmtl_log_failure("vk: vkAllocateCommandBuffers FAILED -> -2"));
    assert(nvmtl_log_failure("vk: vkAllocateMemory refused the imported host pointer -> -1000072003"));
    assert(!nvmtl_log_failure("vk: queue submit -> 0"));
    assert(!nvmtl_log_failure("default cached coherent memory type 0"));
    assert(!nvmtl_log_failure(NULL));
}
