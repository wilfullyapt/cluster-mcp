/* Wardens job schema (for restricted runner)
 * Signed JSON payload verified by runner before execution.
 */

#ifndef WARDENS_JOB_H
#define WARDENS_JOB_H

#include <stdint.h>

typedef struct {
    char job_id[64];
    char allowlist_key[64];   /* e.g. "restart-immich", "collect-logs" */
    char args[1024];          /* JSON or key=value string */
    uint32_t timeout_sec;
    uint64_t mem_limit_bytes;
    uint32_t cpu_limit_percent;
    char signature[512];      /* base64 or hex of signature over payload */
} job_request_t;

#endif /* WARDENS_JOB_H */