/* Wardens Collector — LXC + permissions → ClusterMCP
 *
 * Config (env):
 *   WARDEN_NODE       required node name (e.g. pvenodeone)
 *   CLUSTERMCP_URL    base URL (default http://127.0.0.1:8000)
 *   MCP_API_KEY       optional X-API-Key
 *   WARDEN_VERSION    default 0.2.0
 */

#include <curl/curl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../shared/visibility.h"

#define WARDENS_MAX_LXC 64
#define JSON_BUF 65536

int collect_all_lxc(lxc_visibility_t *out, size_t max, size_t *count, const char *node_name);
int collect_permission_diag(permission_diag_t *out, const char *target_path);

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

    if (append_fmt(json, size, &used, "}") != 0) {
        return -1;
    }
    return 0;
}

static int build_register_json(const char *node, const char *version, char *json, size_t size) {
    size_t used = 0;
    char esc[256];
    json[0] = '\0';
    if (json_escape_into(esc, sizeof(esc), node) != 0) {
        return -1;
    }
    if (append_fmt(json, size, &used, "{\"node\":\"%s\",", esc) != 0) {
        return -1;
    }
    if (json_escape_into(esc, sizeof(esc), version) != 0) {
        return -1;
    }
    if (append_fmt(
            json,
            size,
            &used,
            "\"warden_version\":\"%s\","
            "\"collector_caps\":[\"lxc:full\",\"permissions:audit\"],"
            "\"runner_allowlist\":[],"
            "\"seccomp_profile\":\"none\","
            "\"resource_limits\":{\"max_mem_mb\":256}}",
            esc
        ) != 0) {
        return -1;
    }
    return 0;
}

static size_t discard_body(char *ptr, size_t size, size_t nmemb, void *userdata) {
    (void)ptr;
    (void)userdata;
    return size * nmemb;
}

static int http_post_json(const char *url, const char *api_key, const char *json_body) {
    CURL *curl = curl_easy_init();
    struct curl_slist *headers = NULL;
    CURLcode res;
    long http_code = 0;
    char auth_hdr[512];

    if (!curl) {
        return -1;
    }

    headers = curl_slist_append(headers, "Content-Type: application/json");
    if (api_key && api_key[0] != '\0') {
        snprintf(auth_hdr, sizeof(auth_hdr), "X-API-Key: %s", api_key);
        headers = curl_slist_append(headers, auth_hdr);
    }

    curl_easy_setopt(curl, CURLOPT_URL, url);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, json_body);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 15L);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, discard_body);

    res = curl_easy_perform(curl);
    if (res == CURLE_OK) {
        curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);
    }

    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);

    if (res != CURLE_OK) {
        fprintf(stderr, "[collector] curl error: %s\n", curl_easy_strerror(res));
        return -1;
    }
    if (http_code < 200 || http_code >= 300) {
        fprintf(stderr, "[collector] HTTP %ld for %s\n", http_code, url);
        return -1;
    }
    return 0;
}

int main(int argc, char **argv) {
    const char *node;
    const char *base_url;
    const char *api_key;
    const char *version;
    char base[512];
    char register_url[512];
    char report_url[512];
    char json[JSON_BUF];
    lxc_visibility_t lxc[WARDENS_MAX_LXC];
    permission_diag_t perm;
    size_t lxc_count = 0;
    size_t n;
    int rc = 0;
    (void)argc;
    (void)argv;

    node = getenv("WARDEN_NODE");
    if (!node || node[0] == '\0') {
        fprintf(stderr, "WARDEN_NODE is required (e.g. export WARDEN_NODE=pvenodeone)\n");
        return 2;
    }
    base_url = env_or("CLUSTERMCP_URL", "http://127.0.0.1:8000");
    api_key = env_or("MCP_API_KEY", "");
    version = env_or("WARDEN_VERSION", "0.2.0");

    n = strlen(base_url);
    if (n >= sizeof(base)) {
        fprintf(stderr, "CLUSTERMCP_URL too long\n");
        return 2;
    }
    memcpy(base, base_url, n + 1);
    while (n > 0 && base[n - 1] == '/') {
        base[--n] = '\0';
    }
    snprintf(register_url, sizeof(register_url), "%s/wardens/register", base);
    snprintf(report_url, sizeof(report_url), "%s/wardens/collector/report", base);

    fprintf(stderr, "Wardens Collector v%s starting (node=%s mcp=%s)\n", version, node, base);

    if (collect_all_lxc(lxc, WARDENS_MAX_LXC, &lxc_count, node) != 0) {
        fprintf(stderr, "[collector] LXC collection failed (continuing with empty list)\n");
        lxc_count = 0;
    }
    memset(&perm, 0, sizeof(perm));
    if (collect_permission_diag(&perm, "/etc/pve/lxc") != 0) {
        strncpy(perm.target_path, "/etc/pve/lxc", sizeof(perm.target_path) - 1);
        strncpy(perm.mapping_note, "stat failed", sizeof(perm.mapping_note) - 1);
    }

    curl_global_init(CURL_GLOBAL_DEFAULT);

    if (build_register_json(node, version, json, sizeof(json)) != 0) {
        fprintf(stderr, "Failed to build register JSON\n");
        rc = 1;
        goto out;
    }
    if (http_post_json(register_url, api_key, json) != 0) {
        fprintf(stderr, "Register failed\n");
        rc = 1;
    } else {
        fprintf(stderr, "Registered with ClusterMCP.\n");
    }

    if (build_report_json(node, version, lxc, lxc_count, &perm, json, sizeof(json)) != 0) {
        fprintf(stderr, "Failed to build report JSON\n");
        rc = 1;
        goto out;
    }
    fprintf(stderr, "Report JSON bytes: %zu\n", strlen(json));
    if (http_post_json(report_url, api_key, json) != 0) {
        fprintf(stderr, "Report post failed\n");
        rc = 1;
    } else {
        fprintf(stderr, "Posted visibility report (%zu LXC).\n", lxc_count);
    }

out:
    curl_global_cleanup();
    return rc;
}
