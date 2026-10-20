
#include "production.h"

#include <string.h>

void production_init(production_t *p)
{
    memset(p, 0, sizeof(*p));

    p->state = PROD_IDLE;
    p->next_part_id = 1;
}

bool production_configure(production_t *p,
                          production_config_t config)
{
    if (p->state != PROD_IDLE ||
        config.target_parts == 0 ||
        config.cycle_ms == 0) {
        return false;
    }

    p->config = config;
    return true;
}

bool production_start(production_t *p, int64_t now_us)
{
    if (p->state != PROD_IDLE ||
        p->config.target_parts == 0 ||
        p->config.cycle_ms == 0) {
        return false;
    }

    p->produced_parts = 0;
    p->state = PROD_RUNNING;

    p->next_deadline_us =
        now_us + (int64_t)p->config.cycle_ms * 1000;

    return true;
}

bool production_pause(production_t *p)
{
    if (p->state != PROD_RUNNING) {
        return false;
    }

    p->state = PROD_PAUSED;
    p->next_deadline_us = 0;

    return true;
}

bool production_resume(production_t *p, int64_t now_us)
{
    if (p->state != PROD_PAUSED) {
        return false;
    }

    p->state = PROD_RUNNING;

    // Start a fresh production cycle.
    p->next_deadline_us =
        now_us + (int64_t)p->config.cycle_ms * 1000;

    return true;
}

bool production_stop(production_t *p)
{
    if (p->state != PROD_RUNNING &&
        p->state != PROD_PAUSED) {
        return false;
    }

    p->state = PROD_IDLE;
    p->next_deadline_us = 0;

    return true;
}

bool production_update(production_t *p,
                       int64_t now_us,
                       production_event_t *event)
{
    if (p->state != PROD_RUNNING ||
        now_us < p->next_deadline_us) {
        return false;
    }

    // Generate one virtual part.
    event->part_id = p->next_part_id++;
    p->produced_parts++;

    event->produced_count = p->produced_parts;
    event->batch_production_finished = false;

    if (p->produced_parts >= p->config.target_parts) {
        p->state = PROD_IDLE;
        p->next_deadline_us = 0;
        event->batch_production_finished = true;
    } else {
        int64_t period_us =
            (int64_t)p->config.cycle_ms * 1000;

        p->next_deadline_us += period_us;

        // Skip missed deadlines rather than burst parts.
        if (p->next_deadline_us <= now_us) {
            p->next_deadline_us = now_us + period_us;
        }
    }

    return true;
}
