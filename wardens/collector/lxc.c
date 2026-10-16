/* LXC visibility collection (lxc:full) - improved parsing */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dirent.h>
#include <ctype.h>
#include "../shared/visibility.h"

static void trim(char *str) {
    char *start = str;
    while (isspace(*start)) start++;
    char *end = start + strlen(start) - 1;
    while (end > start && isspace(*end)) *end-- = '\0';
    memmove(str, start, strlen(start) + 1);
}

int collect_lxc_visibility(lxc_visibility_t *out, const char *node_name) {
    DIR *dir;
    struct dirent *entry;
    char path[512];
    FILE *f;
    char line[512];
    char key[128], value[384];

    strncpy(out->node, node_name, sizeof(out->node) - 1);
    out->vmid = 0;
    strncpy(out->status, "unknown", sizeof(out->status) - 1);
    out->unprivileged = false;

    dir = opendir("/etc/pve/lxc");
    if (!dir) {
        perror("opendir /etc/pve/lxc");
        return -1;
    }

    while ((entry = readdir(dir)) != NULL) {
        if (strstr(entry->d_name, ".conf") == NULL) continue;

        snprintf(path, sizeof(path), "/etc/pve/lxc/%s", entry->d_name);
        f = fopen(path, "r");
        if (!f) continue;

        sscanf(entry->d_name, "%d.conf", &out->vmid);

        while (fgets(line, sizeof(line), f)) {
            if (sscanf(line, "%127[^=]=%383[^\n]", key, value) == 2) {
                trim(key);
                trim(value);

                if (strcmp(key, "hostname") == 0) {
                    strncpy(out->hostname, value, sizeof(out->hostname) - 1);
                } else if (strcmp(key, "rootfs") == 0) {
                    strncpy(out->rootfs, value, sizeof(out->rootfs) - 1);
                } else if (strcmp(key, "net0") == 0) {
                    strncat(out->mounts, value, sizeof(out->mounts) - strlen(out->mounts) - 1);
                    strncat(out->mounts, ";", sizeof(out->mounts) - strlen(out->mounts) - 1);
                } else if (strcmp(key, "unprivileged") == 0) {
                    out->unprivileged = (atoi(value) == 1);
                } else if (strcmp(key, "memory") == 0) {
                    // could parse memory limit
                }
            }
        }
        fclose(f);
        break; // first container for now
    }
    closedir(dir);

    printf("[collector] LXC visibility parsed (node=%s, vmid=%d, hostname=%s, unpriv=%d)\n",
           node_name, out->vmid, out->hostname, out->unprivileged);
    return 0;
}
