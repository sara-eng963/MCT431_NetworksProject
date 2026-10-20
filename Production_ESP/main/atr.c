
#include "atr.h"
#include <string.h>


bool atr_encode(
    uint16_t test_id,
    uint32_t seq,
    const uint8_t *payload,
    uint16_t payload_len,
    uint8_t *output,
    size_t output_capacity,
    size_t *output_len)
{
    // 1. Validate pointers
    if (output == NULL || output_len == NULL ||
        (payload_len > 0 && payload == NULL)) {
        return false;
    }

    *output_len = 0;

    // 2. Check output buffer capacity
    size_t total_size =
        ATR_HEADER_SIZE + (size_t)payload_len + ATR_CRC_SIZE;

    if (output_capacity < total_size) {
        return false;
    }

    // 3. Encode the 8-byte header (big-endian)
    output[0] = (uint8_t)(test_id >> 8);
    output[1] = (uint8_t)(test_id);

    output[2] = (uint8_t)(seq >> 24);
    output[3] = (uint8_t)(seq >> 16);
    output[4] = (uint8_t)(seq >> 8);
    output[5] = (uint8_t)(seq);

    output[6] = (uint8_t)(payload_len >> 8);
    output[7] = (uint8_t)(payload_len);

    // 4. Copy payload
    if (payload_len > 0) {
        memcpy(output + ATR_HEADER_SIZE,
               payload,
               payload_len);
    }

    // 5. Calculate CRC over header + payload
    size_t data_size = ATR_HEADER_SIZE + (size_t)payload_len;

    uint16_t crc = atr_crc16(output, data_size);

    // 6. Append CRC (big-endian)
    output[data_size]     = (uint8_t)(crc >> 8);
    output[data_size + 1] = (uint8_t)(crc);

    // 7. Return encoded size
    *output_len = total_size;

    return true;
}


bool atr_decode(
    const uint8_t *input,
    size_t input_len,
    atr_record_t *record)
{
    // 1. Validate pointers and minimum record size
    if (input == NULL || record == NULL ||
        input_len < ATR_HEADER_SIZE + ATR_CRC_SIZE) {
        return false;
    }

    // 2. Extract the declared payload length
    uint16_t payload_len =
        ((uint16_t)input[6] << 8) |
        input[7];

    // 3. Validate the complete record size
    size_t expected_size =
        ATR_HEADER_SIZE + (size_t)payload_len + ATR_CRC_SIZE;

    if (input_len != expected_size) {
        return false;
    }

    // 4. Extract the received CRC
    size_t crc_offset = ATR_HEADER_SIZE + payload_len;

    uint16_t received_crc =
        ((uint16_t)input[crc_offset] << 8) |
        input[crc_offset + 1];

    // 5. Independently calculate and verify CRC
    uint16_t calculated_crc =
        atr_crc16(input, crc_offset);

    if (received_crc != calculated_crc) {
        return false;
    }

    // 6. Extract header fields
    record->test_id =
        ((uint16_t)input[0] << 8) |
        input[1];

    record->seq =
        ((uint32_t)input[2] << 24) |
        ((uint32_t)input[3] << 16) |
        ((uint32_t)input[4] << 8) |
        input[5];

    record->payload_len = payload_len;
    record->payload = input + ATR_HEADER_SIZE;

    return true;
}


uint16_t atr_crc16(const uint8_t *data, size_t length)
{
    uint16_t crc = 0xFFFF;

    for (size_t i = 0; i < length; i++) {
        crc ^= (uint16_t)data[i] << 8;

        for (int bit = 0; bit < 8; bit++) {
            if (crc & 0x8000) {
                crc = (uint16_t)((crc << 1) ^ 0x1021);
            } else {
                crc = (uint16_t)(crc << 1);
            }
        }
    }

    return crc;
}
