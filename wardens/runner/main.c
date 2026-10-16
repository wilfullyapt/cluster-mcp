/* Wardens Restricted Job Runner - Phase 0 skeleton
 * Verifies signed jobs against allow-list, applies seccomp + limits, executes, audits.
 */

#include <stdio.h>
#include "../shared/job.h"

int main(int argc, char **argv) {
    printf("Wardens Runner v0.1 starting (restricted mode)...\n");
    // TODO:
    // - Load allow-list config
    // - Receive job (mTLS from MCP)
    // - Verify signature + allowlist_key
    // - Apply seccomp-bpf, cgroups limits, timeout
    // - Execute only permitted command
    // - Log full audit record back to MCP
    // - Never accept unsigned or out-of-list jobs
    printf("Runner skeleton ready. Implement verification + seccomp next.\n");
    return 0;
}