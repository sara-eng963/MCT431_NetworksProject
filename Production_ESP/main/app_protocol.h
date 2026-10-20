
#ifndef APP_PROTOCOL_H
#define APP_PROTOCOL_H

#include <stdint.h>
#include "production.h"

#define APP_ATR_ID       0U
#define APP_STATUS_SIZE  6U

typedef enum {
    APP_MSG_STATUS = 1
} app_message_type_t;

void app_encode_status(
    uint8_t output[APP_STATUS_SIZE],
    production_state_t state,
    uint32_t produced_parts
);

#endif
