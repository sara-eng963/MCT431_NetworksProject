#ifndef INSPECTION_H
#define INSPECTION_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

enum { INS_CONFIGURE=16, INS_JOB=17, INS_REPLY=18, INS_HEARTBEAT=19, INS_STATUS=20,
       INS_RESET=21 };
enum { INS_IDLE=0, INS_BUSY=1, INS_FAULT=2 };
enum { INS_DELIVERY=1, INS_ACCEPTANCE=2, INS_COMPLETION=3 };
enum { INS_OK=0, INS_INVALID=1, INS_STATE=2, INS_STALE=3, INS_CONFLICT=4 };
enum { INS_NONE=0, INS_PASS=1, INS_FAIL=2 };
typedef void (*inspection_send_fn)(const uint8_t *,size_t,void *);
typedef struct {
    uint32_t boot_id,batch_id,last_id,inspection_ms,rule_n,rule_k;
    uint64_t part_id;
    uint8_t state,last_request[25],last_length,last_result,last_verdict;
    bool have_request,complete;
    int64_t completion_us,heartbeat_us,status_us;
    inspection_send_fn send;
    void *context;
} inspection_t;
void inspection_init(inspection_t *,uint32_t,inspection_send_fn,void *);
void inspection_receive(inspection_t *,const uint8_t *,size_t,int64_t);
void inspection_tick(inspection_t *,int64_t);
void inspection_disconnect(inspection_t *);
#endif
