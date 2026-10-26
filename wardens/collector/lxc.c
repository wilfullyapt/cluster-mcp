/* LXC visibility collection (lxc:full) — enumerate all /etc/pve/lxc conf files */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dirent.h>
#include <ctype.h>
#include "../shared/visibility.h"

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

static void clear_lxc(lxc_visibility_t *out, const char *node_name) {
    memset(out, 0, sizeof(*out));
    if (node_name) {
        strncpy(out->node, node_name, sizeof(out->node) - 1);
    }
    strncpy(out->status, "unknown", sizeof(out->status) - 1);
}

static int parse_lxc_conf(lxc_visibility_t *out, const char *path, int vmid, const char *node_name) {
    FILE *f;
    char line[512];
    char key[128], value[384];

    clear_lxc(out, node_name);
    out->vmid = vmid;
    snprintf(out->config_path, sizeof(out->config_path), "%s", path);

    f = fopen(path, "r");
    if (!f) {
        return -1;
    }

    while (fgets(line, sizeof(line), f)) {
        if (sscanf(line, "%127[^=]=%383[^\n]", key, value) != 2) {
            continue;
        }
        trim(key);
        trim(value);

        if (strcmp(key, "hostname") == 0) {
            snprintf(out->hostname, sizeof(out->hostname), "%s", value);
        } else if (strcmp(key, "rootfs") == 0) {
            snprintf(out->rootfs, sizeof(out->rootfs), "%s", value);
        } else if (strcmp(key, "mp0") == 0 || strncmp(key, "mp", 2) == 0 ||
                   strcmp(key, "net0") == 0 || strncmp(key, "net", 3) == 0) {
            size_t used = strlen(out->mounts);
            if (used + strlen(key) + strlen(value) + 3 < sizeof(out->mounts)) {
                if (used > 0) {
                    strncat(out->mounts, ";", sizeof(out->mounts) - used - 1);
                    used = strlen(out->mounts);
                }
                strncat(out->mounts, key, sizeof(out->mounts) - used - 1);
                used = strlen(out->mounts);
                strncat(out->mounts, "=", sizeof(out->mounts) - used - 1);
                used = strlen(out->mounts);
                strncat(out->mounts, value, sizeof(out->mounts) - used - 1);
            }
        } else if (strcmp(key, "unprivileged") == 0) {
            out->unprivileged = (atoi(value) == 1);
        } else if (strcmp(key, "lxc.idmap") == 0 || strcmp(key, "idmap") == 0) {
            size_t used = strlen(out->idmap);
            if (used + strlen(value) + 2 < sizeof(out->idmap)) {
                if (used > 0) {
                    strncat(out->idmap, ";", sizeof(out->idmap) - used - 1);
                }
                strncat(out->idmap, value, sizeof(out->idmap) - strlen(out->idmap) - 1);
            }
        } else if (strcmp(key, "cores") == 0) {
            out->cores = (uint32_t)atoi(value);
        } else if (strcmp(key, "memory") == 0) {
            /* conf memory is MiB */
            out->memory_used = (uint64_t)atoll(value) * 1024ULL * 1024ULL;
        } else if (strcmp(key, "ostype") == 0) {
            /* pack ostype into status prefix if still unknown */
            if (strcmp(out->status, "unknown") == 0) {
                snprintf(out->status, sizeof(out->status), "ostype:%s", value);
            }
        } else if (strcmp(key, "onboot") == 0) {
            size_t used = strlen(out->mounts);
            if (used + 16 < sizeof(out->mounts)) {
                if (used) {
                    strncat(out->mounts, ";", sizeof(out->mounts) - used - 1);
                }
                strncat(out->mounts, "onboot=", sizeof(out->mounts) - strlen(out->mounts) - 1);
                strncat(out->mounts, value, sizeof(out->mounts) - strlen(out->mounts) - 1);
            }
        } else if (strcmp(key, "tags") == 0 || strcmp(key, "description") == 0) {
            size_t used = strlen(out->idmap);
            if (used + strlen(key) + strlen(value) + 4 < sizeof(out->idmap)) {
                if (used) {
                    strncat(out->idmap, ";", sizeof(out->idmap) - used - 1);
                }
                strncat(out->idmap, key, sizeof(out->idmap) - strlen(out->idmap) - 1);
                strncat(out->idmap, "=", sizeof(out->idmap) - strlen(out->idmap) - 1);
                strncat(out->idmap, value, sizeof(out->idmap) - strlen(out->idmap) - 1);
            }
        }
    }
    fclose(f);
    return 0;
}

int collect_all_lxc(lxc_visibility_t *out, size_t max, size_t *count, const char *node_name) {
    DIR *dir;
    struct dirent *entry;
    char path[256];
    int vmid;

    if (!out || !count || max == 0) {
        return -1;
    }
    *count = 0;

    dir = opendir("/etc/pve/lxc");
    if (!dir) {
        perror("opendir /etc/pve/lxc");
        return -1;
    }

    while ((entry = readdir(dir)) != NULL && *count < max) {
        if (!strstr(entry->d_name, ".conf")) {
            continue;
        }
        if (sscanf(entry->d_name, "%d.conf", &vmid) != 1) {
            continue;
        }
        snprintf(path, sizeof(path), "/etc/pve/lxc/%.200s", entry->d_name);
        if (parse_lxc_conf(&out[*count], path, vmid, node_name) == 0) {
            (*count)++;
        }
    }
    closedir(dir);

    fprintf(stderr, "[collector] LXC visibility: %zu container(s) on node=%s\n", *count, node_name);

    /* Enrich status from pct list when available */
    {
        FILE *pf = popen("pct list 2>/dev/null", "r");
        char line[256];
        if (pf) {
            if (fgets(line, sizeof(line), pf)) {
                /* skip header */
            }
            while (fgets(line, sizeof(line), pf)) {
                int id = 0;
                char st[64] = "";
                if (sscanf(line, "%d %63s", &id, st) >= 2) {
                    for (size_t i = 0; i < *count; i++) {
                        if (out[i].vmid == id) {
                            snprintf(out[i].status, sizeof(out[i].status), "%s", st);
                        }
                    }
                }
            }
            pclose(pf);
        }
    }
    return 0;
}

/* Back-compat single-entry helper (first container). */
int collect_lxc_visibility(lxc_visibility_t *out, const char *node_name) {
    size_t n = 0;
    if (collect_all_lxc(out, 1, &n, node_name) != 0) {
        return -1;
    }
    if (n == 0) {
        clear_lxc(out, node_name);
    }
    return 0;
}
