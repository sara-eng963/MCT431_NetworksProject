
#ifndef PRODUCTION_H
#define PRODUCTION_H

#include <stdbool.h>
#include <stdint.h>

typedef enum {
    PROD_IDLE,
    PROD_RUNNING,
    PROD_PAUSED,
    PROD_FAULT
} production_state_t;

typedef struct {
    uint32_t target_parts;
    uint32_t cycle_ms;
} production_config_t;

typedef struct {
    uint64_t part_id;
    uint32_t produced_count;
    bool batch_production_finished;
} production_event_t;

typedef struct {
    production_state_t state;
    production_config_t config;

    uint32_t produced_parts;
    uint64_t next_part_id;
    int64_t next_deadline_us;
} production_t;

// Lifecycle
void production_init(production_t *p);
bool production_configure(production_t *p,
                          production_config_t config);

// State transitions
bool production_start(production_t *p, int64_t now_us);
bool production_pause(production_t *p);
bool production_resume(production_t *p, int64_t now_us);
bool production_stop(production_t *p);

// Called periodically by the owning task
bool production_update(production_t *p,
                       int64_t now_us,
                       production_event_t *event);

#endif
