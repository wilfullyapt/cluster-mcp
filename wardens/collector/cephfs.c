/* CephFS-ish mount visibility from LXC conf mp* lines + storage.cfg hints */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <dirent.h>

#include "../shared/visibility.h"

#define MAX_CEPHFS 16

static void trim(char *str) {
    char *start = str;
    while (*start && isspace((unsigned char)*start)) {
        start++;
    }
    if (start != str) {
        memmove(str, start, strlen(start) + 1);
    }
    size_t len = strlen(str);
    while (len > 0 && isspace((unsigned char)str[len - 1])) {
        str[--len] = '\0';
    }
}

static int looks_cephish(const char *s) {
    if (!s) {
        return 0;
    }
    if (strstr(s, "ceph") || strstr(s, "Ceph") || strstr(s, "CEPH")) {
        return 1;
    }
    if (strstr(s, "/mnt/pve/") || strstr(s, "cephfs")) {
        return 1;
    }
    return 0;
}

/* Parse volume=path,mp=... style mp values */
static void fill_from_mp_value(cephfs_visibility_t *out, const char *value) {
    char buf[512];
    char *save = NULL;
    char *tok;

    memset(out, 0, sizeof(*out));
    snprintf(buf, sizeof(buf), "%s", value);
    for (tok = strtok_r(buf, ",", &save); tok; tok = strtok_r(NULL, ",", &save)) {
        char *eq = strchr(tok, '=');
        if (!eq) {
            if (out->host_path[0] == '\0' && looks_cephish(tok)) {
                snprintf(out->host_path, sizeof(out->host_path), "%s", tok);
            }
            continue;
        }
        *eq = '\0';
        char *k = tok;
        char *v = eq + 1;
        if (strcmp(k, "mp") == 0 || strcmp(k, "volume") == 0) {
            if (strcmp(k, "mp") == 0) {
                snprintf(out->container_mount, sizeof(out->container_mount), "%s", v);
            } else {
                snprintf(out->host_path, sizeof(out->host_path), "%s", v);
                if (looks_cephish(v)) {
                    snprintf(out->cephfs_name, sizeof(out->cephfs_name), "%s", v);
                }
            }
        } else if (strcmp(k, "subvol") == 0 || strcmp(k, "subvolume") == 0) {
            snprintf(out->subvolume, sizeof(out->subvolume), "%s", v);
        }
    }
    if (out->host_path[0] == '\0' && looks_cephish(value)) {
        snprintf(out->host_path, sizeof(out->host_path), "%s", value);
    }
}

int collect_cephfs_visibility(cephfs_visibility_t *out, size_t max, size_t *count) {
    DIR *dir;
    struct dirent *entry;
    char path[512];
    char line[512];
    char key[128], value[384];
    FILE *f;

    if (!out || !count || max == 0) {
        return -1;
    }
    *count = 0;

    dir = opendir("/etc/pve/lxc");
    if (!dir) {
        return -1;
    }
    while ((entry = readdir(dir)) != NULL && *count < max) {
        if (!strstr(entry->d_name, ".conf")) {
            continue;
        }
        snprintf(path, sizeof(path), "/etc/pve/lxc/%.200s", entry->d_name);
        f = fopen(path, "r");
        if (!f) {
            continue;
        }
        while (fgets(line, sizeof(line), f) && *count < max) {
            if (sscanf(line, "%127[^=]=%383[^\n]", key, value) != 2) {
                continue;
            }
            trim(key);
            trim(value);
            if (strncmp(key, "mp", 2) != 0) {
                continue;
            }
            if (!looks_cephish(value) && !looks_cephish(key)) {
                continue;
            }
            fill_from_mp_value(&out[*count], value);
            if (out[*count].host_path[0] || out[*count].container_mount[0] || out[*count].subvolume[0]) {
                (*count)++;
            }
        }
        fclose(f);
    }
    closedir(dir);

    /* storage.cfg cephfs stanzas (name only) */
    f = fopen("/etc/pve/storage.cfg", "r");
    if (f) {
        char cur_name[64] = "";
        int in_cephfs = 0;
        while (fgets(line, sizeof(line), f) && *count < max) {
            if (strncmp(line, "cephfs:", 7) == 0) {
                in_cephfs = 1;
                sscanf(line + 7, "%63s", cur_name);
                continue;
            }
            if (line[0] && !isspace((unsigned char)line[0])) {
                in_cephfs = 0;
                cur_name[0] = '\0';
                continue;
            }
            if (in_cephfs && cur_name[0] && *count < max) {
                /* one row per named cephfs storage */
                int already = 0;
                for (size_t i = 0; i < *count; i++) {
                    if (strcmp(out[i].cephfs_name, cur_name) == 0) {
                        already = 1;
                        break;
                    }
                }
                if (!already) {
                    memset(&out[*count], 0, sizeof(out[*count]));
                    snprintf(out[*count].cephfs_name, sizeof(out[*count].cephfs_name), "%s", cur_name);
                    snprintf(out[*count].host_path, sizeof(out[*count].host_path), "/mnt/pve/%s", cur_name);
                    (*count)++;
                }
                in_cephfs = 0; /* only once per stanza header */
            }
        }
        fclose(f);
    }

    fprintf(stderr, "[collector] cephfs visibility entries: %zu\n", *count);
    return 0;
}
