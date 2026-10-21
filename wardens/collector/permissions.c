/* Basic permission/UID diagnostics collector */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include "../shared/visibility.h"

int collect_permission_diag(permission_diag_t *out, const char *target_path) {
    struct stat st;

    strncpy(out->target_path, target_path, sizeof(out->target_path) - 1);

    if (stat(target_path, &st) != 0) {
        strncpy(out->mapping_note, "stat failed", sizeof(out->mapping_note) - 1);
        return -1;
    }

    snprintf(out->effective_uid, sizeof(out->effective_uid), "%d", st.st_uid);
    snprintf(out->effective_gid, sizeof(out->effective_gid), "%d", st.st_gid);

    out->readable = (access(target_path, R_OK) == 0);
    out->writable = (access(target_path, W_OK) == 0);
    out->executable = (access(target_path, X_OK) == 0);

    snprintf(out->capabilities, sizeof(out->capabilities), "mode=%o", (unsigned)(st.st_mode & 07777));
    strncpy(out->mapping_note, "basic stat + access check", sizeof(out->mapping_note) - 1);

    printf("[collector] Permission diag for %s (uid=%s, readable=%d)\n",
           target_path, out->effective_uid, out->readable);
    return 0;
}
