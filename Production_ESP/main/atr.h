
#ifndef ATR_H
#define ATR_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

bool atr_encode(
    uint16_t test_id,
    uint32_t seq,
    const uint8_t *payload,
    uint16_t payload_len,
    uint8_t *output,
    size_t output_capacity,
    size_t *output_len
);


typedef struct {
    uint16_t test_id;
    uint32_t seq;
    uint16_t payload_len;
    const uint8_t *payload;
} atr_record_t;

bool atr_decode(
    const uint8_t *input,
    size_t input_len,
    atr_record_t *record
);


#define ATR_HEADER_SIZE 8U
#define ATR_CRC_SIZE    2U

uint16_t atr_crc16(const uint8_t *data, size_t length);

#endif
