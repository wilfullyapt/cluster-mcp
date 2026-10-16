/* Wardens Collector - expanded demo (LXC + Permissions + JSON + HTTP) */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <curl/curl.h>
#include "../shared/visibility.h"

int collect_lxc_visibility(lxc_visibility_t *out, const char *node_name);
int collect_permission_diag(permission_diag_t *out, const char *target_path);

static void build_report_json(const lxc_visibility_t *lxc, const permission_diag_t *perm, char *json, size_t size) {
    snprintf(json, size,
        "{"
        "\"node\":\"%s\","
        "\"lxc\":{\"vmid\":%d,\"hostname\":\"%s\",\"rootfs\":\"%s\",\"unprivileged\":%s},"
        "\"permission\":{\"path\":\"%s\",\"uid\":\"%s\",\"readable\":%s}"
        "}",
        lxc->node,
        lxc->vmid, lxc->hostname, lxc->rootfs, lxc->unprivileged ? "true" : "false",
        perm->target_path, perm->effective_uid, perm->readable ? "true" : "false");
}

int post_to_mcp(const char *json) {
    CURL *curl = curl_easy_init();
    if (!curl) return -1;

    struct curl_slist *headers = NULL;
    headers = curl_slist_append(headers, "Content-Type: application/json");

    curl_easy_setopt(curl, CURLOPT_URL, "http://192.168.0.233:8000/wardens/collector/report");
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, json);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 10L);

    CURLcode res = curl_easy_perform(curl);
    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);

    return (res == CURLE_OK) ? 0 : -1;
}

int main(int argc, char **argv) {
    printf("Wardens Collector v0.2 starting (LXC + Permissions)...\n");

    lxc_visibility_t lxc;
    permission_diag_t perm;

    collect_lxc_visibility(&lxc, "pvenodeone");
    collect_permission_diag(&perm, "/etc/pve/lxc");

    char json[4096];
    build_report_json(&lxc, &perm, json, sizeof(json));
    printf("Report JSON: %s\n", json);

    if (post_to_mcp(json) == 0) {
        printf("Posted to MCP.\n");
    } else {
        printf("Post failed (libcurl + network required).\n");
    }

    return 0;
}
