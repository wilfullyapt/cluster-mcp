/* Host visibility — loadavg, memory, uptime, kernel, pveversion */

#include <stdio.h>
#include <string.h>
#include <sys/utsname.h>

#include "../shared/visibility.h"

int collect_host_visibility(host_visibility_t *out) {
    FILE *f;
    char line[256];
    unsigned long long mem_total_kb = 0, mem_avail_kb = 0;
    struct utsname uts;

    memset(out, 0, sizeof(*out));

    f = fopen("/proc/loadavg", "r");
    if (f) {
        if (fscanf(f, "%lf %lf %lf", &out->loadavg_1, &out->loadavg_5, &out->loadavg_15) == 3) {
            out->valid = true;
        }
        fclose(f);
    }

    f = fopen("/proc/meminfo", "r");
    if (f) {
        while (fgets(line, sizeof(line), f)) {
            if (sscanf(line, "MemTotal: %llu kB", &mem_total_kb) == 1) {
                continue;
            }
            if (sscanf(line, "MemAvailable: %llu kB", &mem_avail_kb) == 1) {
                continue;
            }
        }
        fclose(f);
        out->mem_total_bytes = mem_total_kb * 1024ULL;
        out->mem_available_bytes = mem_avail_kb * 1024ULL;
        out->valid = true;
    }

    f = fopen("/proc/uptime", "r");
    if (f) {
        if (fscanf(f, "%lf", &out->uptime_seconds) == 1) {
            out->valid = true;
        }
        fclose(f);
    }

    if (uname(&uts) == 0) {
        snprintf(out->kernel, sizeof(out->kernel), "%s", uts.release);
        out->valid = true;
    }

    f = popen("pveversion 2>/dev/null | head -1", "r");
    if (f) {
        if (fgets(line, sizeof(line), f)) {
            size_t n = strlen(line);
            while (n > 0 && (line[n - 1] == '\n' || line[n - 1] == '\r')) {
                line[--n] = '\0';
            }
            snprintf(out->pve_version, sizeof(out->pve_version), "%s", line);
        }
        pclose(f);
    }

    return out->valid ? 0 : -1;
}
