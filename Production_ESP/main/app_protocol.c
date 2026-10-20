
#include "app_protocol.h"

void app_encode_status(
    uint8_t output[APP_STATUS_SIZE],
    production_state_t state,
    uint32_t produced_parts)
{
    // Message type
    output[0] = APP_MSG_STATUS;

    // Current production state
    output[1] = (uint8_t)state;

    // Produced parts (32-bit big-endian)
    output[2] = (uint8_t)(produced_parts >> 24);
    output[3] = (uint8_t)(produced_parts >> 16);
    output[4] = (uint8_t)(produced_parts >> 8);
    output[5] = (uint8_t)produced_parts;
}
