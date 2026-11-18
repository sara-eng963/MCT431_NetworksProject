#ifndef CONTROLLER_H
#define CONTROLLER_H
#include "production.h"
#include <stddef.h>
enum { MSG_STATUS=1, MSG_COMMAND=2, MSG_COMMAND_EVENT=3,
       MSG_PART=4, MSG_PART_ACK=5, MSG_HEARTBEAT=6 };
enum { OP_CONFIGURE=1, OP_START=2, OP_PAUSE=3, OP_RESUME=4, OP_STOP=5 };
enum { PH_DELIVERY=1, PH_ACCEPTANCE=2, PH_COMPLETION=3 };
enum { RES_OK=0, RES_INVALID=1, RES_STATE=2, RES_STALE=3, RES_CONFLICT=4 };
enum { COMMAND_SIZE=22, STATUS_SIZE=18, PART_SIZE=22 };
typedef void (*controller_send_fn)(const uint8_t *, size_t, void *);
typedef struct {
    production_t production;
    uint32_t boot_id, batch_id, last_cmd_id;
    uint8_t last_command[COMMAND_SIZE], last_result, last_state;
    bool have_command, pending;
    uint8_t part[PART_SIZE];
    unsigned attempts;
    int64_t retry_us, heartbeat_us, status_us;
    controller_send_fn send;
    void *send_context;
} controller_t;
void controller_init(controller_t *, uint32_t, controller_send_fn, void *);
void controller_receive(controller_t *, const uint8_t *, size_t, int64_t);
void controller_tick(controller_t *, int64_t);
#endif
