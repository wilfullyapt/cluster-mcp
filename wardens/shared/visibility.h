/* Wardens shared visibility data models (C structs + JSON schema comments)
 * Phase 0 foundation. Stable contracts between collector, runner, and central MCP.
 * All fields are read-only for collector. Runner uses job schema separately.
 */

#ifndef WARDENS_VISIBILITY_H
#define WARDENS_VISIBILITY_H

#include <stdint.h>
#include <stdbool.h>

/* 1. LXC Visibility */
typedef struct {
    char node[64];
    int vmid;
    char hostname[128];
    char status[32];          /* running, stopped, etc. */
    char config_path[256];    /* /etc/pve/lxc/<vmid>.conf or equivalent */
    char rootfs[256];
    char mounts[2048];        /* JSON array of bind mounts + options */
    char idmap[1024];         /* UID/GID mapping string */
    uint64_t memory_used;
    uint32_t cores;
    bool unprivileged;
} lxc_visibility_t;

/* 2. CephFS Visibility */
typedef struct {
    char subvolume[256];
    char host_path[256];
    char container_mount[256];
    char owner[64];           /* effective UID/GID on host */
    char permissions[32];     /* octal or rwx */
    uint64_t quota_bytes;
    uint64_t used_bytes;
    char cephfs_name[64];
} cephfs_visibility_t;

/* 3. Docker / Compose Visibility */
typedef struct {
    char project_name[128];
    char compose_path[256];
    char status[64];          /* up, down, partial */
    char containers[2048];    /* JSON summary of containers in project */
    char networks[512];
    char volumes[512];
    char logs_path[256];      /* path to recent logs if available */
} docker_visibility_t;

/* 4. Permission / UID Diagnostics */
typedef struct {
    char target_path[256];
    char effective_uid[64];
    char effective_gid[64];
    char capabilities[512];   /* capsh or getcap output */
    bool readable;
    bool writable;
    bool executable;
    char mapping_note[256];   /* explanation of idmap or root squash */
} permission_diag_t;

/* 5. Troubleshooting Bundle */
typedef struct {
    char node[64];
    char timestamp[64];
    lxc_visibility_t lxc;     /* embedded or referenced */
    cephfs_visibility_t cephfs[8];
    docker_visibility_t docker[4];
    permission_diag_t perms[8];
    char recent_errors[4096];
    uint64_t loadavg[3];
} troubleshooting_bundle_t;

#endif /* WARDENS_VISIBILITY_H */