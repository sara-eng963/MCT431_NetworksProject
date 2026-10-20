
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "atr.h"
#include "slip.h"

#define PAYLOAD_SIZE 64U

int main(void)
{
    const uint32_t seq = 192;
    const uint16_t test_id = 1;

    uint8_t payload[PAYLOAD_SIZE];

    // Generate payload using the assignment's formula.
    for (size_t i = 0; i < PAYLOAD_SIZE; i++) {
        payload[i] = (uint8_t)(seq + i);
    }

    uint8_t atr[ATR_HEADER_SIZE + PAYLOAD_SIZE + ATR_CRC_SIZE];
    uint8_t framed[2 * sizeof(atr) + 2];
    uint8_t restored[sizeof(atr)];

    size_t atr_len = 0;
    size_t framed_len = 0;
    size_t restored_len = 0;

    // Sender
    assert(atr_encode(test_id, seq, payload, PAYLOAD_SIZE,
                      atr, sizeof(atr), &atr_len));

    assert(slip_encode(atr, atr_len,
                       framed, sizeof(framed), &framed_len));

    // Receiver
    assert(slip_decode(framed, framed_len,
                       restored, sizeof(restored), &restored_len));

    atr_record_t record;

    assert(atr_decode(restored, restored_len, &record));

    // Verify original information was recovered.
    assert(record.test_id == test_id);
    assert(record.seq == seq);
    assert(record.payload_len == PAYLOAD_SIZE);
    assert(memcmp(record.payload, payload, PAYLOAD_SIZE) == 0);

    printf("PASS: ATR + SLIP round trip\n");
    printf("ATR size: %zu bytes\n", atr_len);
    printf("SLIP size: %zu bytes\n", framed_len);

    return 0;
}
