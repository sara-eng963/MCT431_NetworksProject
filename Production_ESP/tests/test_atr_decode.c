
#include <assert.h>
#include <stdint.h>
#include <stdio.h>

#include "atr.h"

int main(void)
{
    uint8_t data[] = {
        0x12, 0x34,
        0x00, 0x00, 0x00, 0x00,
        0x00, 0x10,
        0x00, 0x01, 0x02, 0x03,
        0x04, 0x05, 0x06, 0x07,
        0x08, 0x09, 0x0A, 0x0B,
        0x0C, 0x0D, 0x0E, 0x0F,
        0x5A, 0x74
    };

    atr_record_t record;

    // Test 1: Valid record
    assert(atr_decode(data, sizeof(data), &record));

    assert(record.test_id == 0x1234);
    assert(record.seq == 0);
    assert(record.payload_len == 16);

    for (int i = 0; i < 16; i++) {
        assert(record.payload[i] == (uint8_t)i);
    }

    printf("PASS: Valid ATR decoding\n");

    // Test 2: Corrupted payload
    data[8] ^= 0x01;

    assert(!atr_decode(data, sizeof(data), &record));

    printf("PASS: Corrupted record rejected\n");

    // Restore the original byte
    data[8] ^= 0x01;

    // Test 3: Incomplete record
    assert(!atr_decode(data, sizeof(data) - 1, &record));

    printf("PASS: Incomplete record rejected\n");

    return 0;
}
