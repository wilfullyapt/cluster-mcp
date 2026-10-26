/* Wardens Collector bridge — LXC + permissions → stdout JSON
 *
 * ClusterMCP initiates collection over SSH. This binary does not know where
 * MCP lives and never opens a network connection.
 *
 * Config (env):
 *   WARDEN_NODE       required node name (e.g. pvenodeone)
 *   WARDEN_VERSION    default 0.3.0
 *
 * stdout: one CollectorReport JSON document
 * stderr: diagnostics only
 */

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../shared/visibility.h"

#define WARDENS_MAX_LXC 64
#define JSON_BUF 65536

int collect_all_lxc(lxc_visibility_t *out, size_t max, size_t *count, const char *node_name);
int collect_permission_diag(permission_diag_t *out, const char *target_path);
int collect_host_visibility(host_visibility_t *out);
int collect_cephfs_visibility(cephfs_visibility_t *out, size_t max, size_t *count);

static const char *env_or(const char *key, const char *fallback) {
    const char *v = getenv(key);
    if (v && v[0] != '\0') {
        return v;
    }
    return fallback;
}

/* Append JSON-escaped string (no surrounding quotes). Returns 0 on success. */
static int json_escape_into(char *dst, size_t dst_sz, const char *src) {
    size_t j = 0;
    if (!src) {
        src = "";
    }
    for (size_t i = 0; src[i] != '\0'; i++) {
        unsigned char c = (unsigned char)src[i];
        const char *rep = NULL;
        char tmp[8];
        size_t rep_len = 0;

        switch (c) {
            case '\\':
                rep = "\\\\";
                rep_len = 2;
                break;
            case '"':
                rep = "\\\"";
                rep_len = 2;
                break;
            case '\n':
                rep = "\\n";
                rep_len = 2;
                break;
            case '\r':
                rep = "\\r";
                rep_len = 2;
                break;
            case '\t':
                rep = "\\t";
                rep_len = 2;
                break;
            default:
                if (c < 0x20) {
                    snprintf(tmp, sizeof(tmp), "\\u%04x", c);
                    rep = tmp;
                    rep_len = 6;
                } else {
                    tmp[0] = (char)c;
                    tmp[1] = '\0';
                    rep = tmp;
                    rep_len = 1;
                }
                break;
        }
        if (j + rep_len + 1 >= dst_sz) {
            return -1;
        }
        memcpy(dst + j, rep, rep_len);
        j += rep_len;
    }
    dst[j] = '\0';
    return 0;
}

static int append_fmt(char *buf, size_t buf_sz, size_t *used, const char *fmt, ...) {
    va_list ap;
    int n;
    if (*used >= buf_sz) {
        return -1;
    }
    va_start(ap, fmt);
    n = vsnprintf(buf + *used, buf_sz - *used, fmt, ap);
    va_end(ap);
    if (n < 0 || (size_t)n >= buf_sz - *used) {
        return -1;
    }
    *used += (size_t)n;
    return 0;
}

static int build_report_json(
    const char *node,
    const char *version,
    const lxc_visibility_t *lxc,
    size_t lxc_count,
    const permission_diag_t *perm,
    const host_visibility_t *host,
    const cephfs_visibility_t *cephfs,
    size_t cephfs_count,
    char *json,
    size_t size
) {
    size_t used = 0;
    char esc[1024];

    json[0] = '\0';
    if (append_fmt(json, size, &used, "{") != 0) {
        return -1;
    }

    if (json_escape_into(esc, sizeof(esc), node) != 0) {
        return -1;
    }
    if (append_fmt(json, size, &used, "\"node\":\"%s\",", esc) != 0) {
        return -1;
    }

    if (json_escape_into(esc, sizeof(esc), version) != 0) {
        return -1;
    }
    if (append_fmt(json, size, &used, "\"warden_version\":\"%s\",", esc) != 0) {
        return -1;
    }

    if (append_fmt(json, size, &used, "\"lxc\":[") != 0) {
        return -1;
    }
    for (size_t i = 0; i < lxc_count; i++) {
        const lxc_visibility_t *e = &lxc[i];
        if (i > 0 && append_fmt(json, size, &used, ",") != 0) {
            return -1;
        }
        if (append_fmt(json, size, &used, "{") != 0) {
            return -1;
        }
        if (append_fmt(json, size, &used, "\"vmid\":%d,", e->vmid) != 0) {
            return -1;
        }

        if (json_escape_into(esc, sizeof(esc), e->hostname) != 0) {
            return -1;
        }
        if (append_fmt(json, size, &used, "\"hostname\":\"%s\",", esc) != 0) {
            return -1;
        }

        if (json_escape_into(esc, sizeof(esc), e->rootfs) != 0) {
            return -1;
        }
        if (append_fmt(json, size, &used, "\"rootfs\":\"%s\",", esc) != 0) {
            return -1;
        }

        if (append_fmt(
                json,
                size,
                &used,
                "\"unprivileged\":%s,",
                e->unprivileged ? "true" : "false"
            ) != 0) {
            return -1;
        }

        if (json_escape_into(esc, sizeof(esc), e->status) != 0) {
            return -1;
        }
        if (append_fmt(json, size, &used, "\"status\":\"%s\",", esc) != 0) {
            return -1;
        }

        if (json_escape_into(esc, sizeof(esc), e->mounts) != 0) {
            return -1;
        }
        if (append_fmt(json, size, &used, "\"mounts\":\"%s\",", esc) != 0) {
            return -1;
        }

        if (json_escape_into(esc, sizeof(esc), e->idmap) != 0) {
            return -1;
        }
        if (append_fmt(json, size, &used, "\"idmap\":\"%s\"", esc) != 0) {
            return -1;
        }

        if (append_fmt(json, size, &used, "}") != 0) {
            return -1;
        }
    }
    if (append_fmt(json, size, &used, "],") != 0) {
        return -1;
    }

    if (perm) {
        if (append_fmt(json, size, &used, "\"permission\":{") != 0) {
            return -1;
        }
        if (json_escape_into(esc, sizeof(esc), perm->target_path) != 0) {
            return -1;
        }
        if (append_fmt(json, size, &used, "\"target_path\":\"%s\",", esc) != 0) {
            return -1;
        }
        if (json_escape_into(esc, sizeof(esc), perm->effective_uid) != 0) {
            return -1;
        }
        if (append_fmt(json, size, &used, "\"effective_uid\":\"%s\",", esc) != 0) {
            return -1;
        }
        if (json_escape_into(esc, sizeof(esc), perm->effective_gid) != 0) {
            return -1;
        }
        if (append_fmt(json, size, &used, "\"effective_gid\":\"%s\",", esc) != 0) {
            return -1;
        }
        if (append_fmt(json, size, &used, "\"readable\":%s,", perm->readable ? "true" : "false") != 0) {
            return -1;
        }
        if (append_fmt(json, size, &used, "\"writable\":%s,", perm->writable ? "true" : "false") != 0) {
            return -1;
        }
        if (append_fmt(json, size, &used, "\"executable\":%s,", perm->executable ? "true" : "false") != 0) {
            return -1;
        }
        if (json_escape_into(esc, sizeof(esc), perm->capabilities) != 0) {
            return -1;
        }
        if (append_fmt(json, size, &used, "\"capabilities\":\"%s\",", esc) != 0) {
            return -1;
        }
        if (json_escape_into(esc, sizeof(esc), perm->mapping_note) != 0) {
            return -1;
        }
        if (append_fmt(json, size, &used, "\"mapping_note\":\"%s\"", esc) != 0) {
            return -1;
        }
        if (append_fmt(json, size, &used, "}") != 0) {
            return -1;
        }
    } else if (append_fmt(json, size, &used, "\"permission\":null") != 0) {
        return -1;
    }

    if (host && host->valid) {
        char esc[256];
        if (append_fmt(json, size, &used, ",\"host\":{") != 0) {
            return -1;
        }
        if (append_fmt(
                json,
                size,
                &used,
                "\"loadavg_1\":%.2f,\"loadavg_5\":%.2f,\"loadavg_15\":%.2f,"
                "\"mem_total_bytes\":%llu,\"mem_available_bytes\":%llu,"
                "\"uptime_seconds\":%.0f,",
                host->loadavg_1,
                host->loadavg_5,
                host->loadavg_15,
                (unsigned long long)host->mem_total_bytes,
                (unsigned long long)host->mem_available_bytes,
                host->uptime_seconds
            ) != 0) {
            return -1;
        }
        if (json_escape_into(esc, sizeof(esc), host->kernel) != 0) {
            return -1;
        }
        if (append_fmt(json, size, &used, "\"kernel\":\"%s\",", esc) != 0) {
            return -1;
        }
        if (json_escape_into(esc, sizeof(esc), host->pve_version) != 0) {
            return -1;
        }
        if (append_fmt(json, size, &used, "\"pve_version\":\"%s\"}", esc) != 0) {
            return -1;
        }
    } else if (append_fmt(json, size, &used, ",\"host\":null") != 0) {
        return -1;
    }

    if (append_fmt(json, size, &used, ",\"cephfs\":[") != 0) {
        return -1;
    }
    for (size_t i = 0; i < cephfs_count; i++) {
        const cephfs_visibility_t *c = &cephfs[i];
        char esc2[512];
        if (i > 0 && append_fmt(json, size, &used, ",") != 0) {
            return -1;
        }
        if (append_fmt(json, size, &used, "{") != 0) {
            return -1;
        }
        if (json_escape_into(esc2, sizeof(esc2), c->subvolume) != 0) {
            return -1;
        }
        if (append_fmt(json, size, &used, "\"subvolume\":\"%s\",", esc2) != 0) {
            return -1;
        }
        if (json_escape_into(esc2, sizeof(esc2), c->host_path) != 0) {
            return -1;
        }
        if (append_fmt(json, size, &used, "\"host_path\":\"%s\",", esc2) != 0) {
            return -1;
        }
        if (json_escape_into(esc2, sizeof(esc2), c->container_mount) != 0) {
            return -1;
        }
        if (append_fmt(json, size, &used, "\"container_mount\":\"%s\",", esc2) != 0) {
            return -1;
        }
        if (json_escape_into(esc2, sizeof(esc2), c->cephfs_name) != 0) {
            return -1;
        }
        if (append_fmt(json, size, &used, "\"cephfs_name\":\"%s\"}", esc2) != 0) {
            return -1;
        }
    }
    if (append_fmt(json, size, &used, "]") != 0) {
        return -1;
    }

    if (append_fmt(json, size, &used, "}") != 0) {
        return -1;
    }
    return 0;
}

int main(int argc, char **argv) {
    const char *node;
    const char *version;
    char json[JSON_BUF];
    lxc_visibility_t lxc[WARDENS_MAX_LXC];
    permission_diag_t perm;
    host_visibility_t host;
    cephfs_visibility_t cephfs[16];
    size_t lxc_count = 0;
    size_t cephfs_count = 0;
    (void)argc;
    (void)argv;

    node = getenv("WARDEN_NODE");
    if (!node || node[0] == '\0') {
        fprintf(stderr, "WARDEN_NODE is required (e.g. export WARDEN_NODE=pvenodeone)\n");
        return 2;
    }
    version = env_or("WARDEN_VERSION", "0.5.0");

    fprintf(stderr, "Wardens bridge v%s collect (node=%s)\n", version, node);

    if (collect_all_lxc(lxc, WARDENS_MAX_LXC, &lxc_count, node) != 0) {
        fprintf(stderr, "[collector] LXC collection failed (continuing with empty list)\n");
        lxc_count = 0;
    }
    memset(&perm, 0, sizeof(perm));
    if (collect_permission_diag(&perm, "/etc/pve/lxc") != 0) {
        strncpy(perm.target_path, "/etc/pve/lxc", sizeof(perm.target_path) - 1);
        strncpy(perm.mapping_note, "stat failed", sizeof(perm.mapping_note) - 1);
    }
    memset(&host, 0, sizeof(host));
    if (collect_host_visibility(&host) != 0) {
        fprintf(stderr, "[collector] host visibility incomplete (continuing)\n");
    }
    memset(cephfs, 0, sizeof(cephfs));
    if (collect_cephfs_visibility(cephfs, 16, &cephfs_count) != 0) {
        cephfs_count = 0;
    }

    if (build_report_json(
            node, version, lxc, lxc_count, &perm, &host, cephfs, cephfs_count, json, sizeof(json)
        ) != 0) {
        fprintf(stderr, "Failed to build report JSON\n");
        return 1;
    }

    fputs(json, stdout);
    fputc('\n', stdout);
    fflush(stdout);
    fprintf(
        stderr,
        "Report JSON bytes: %zu lxc=%zu cephfs=%zu host_valid=%d\n",
        strlen(json),
        lxc_count,
        cephfs_count,
        host.valid ? 1 : 0
    );
    return 0;
}
