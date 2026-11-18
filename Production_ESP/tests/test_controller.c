#include "controller.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static uint8_t messages[128][32];
static size_t sizes[128], count;
static void send_message(const uint8_t *p,size_t n,void *ctx) {
    (void)ctx; assert(count<128 && n<=32);
    memcpy(messages[count],p,n); sizes[count++]=n;
}
static void put32(uint8_t *p,uint32_t v) {
    p[0]=v>>24;p[1]=v>>16;p[2]=v>>8;p[3]=v;
}
static void cmd(controller_t *c,uint32_t id,uint8_t op,uint32_t a,uint32_t b,int64_t now) {
    uint8_t p[22]={MSG_COMMAND};
    put32(p+1,123);put32(p+5,id);put32(p+9,7);p[13]=op;
    put32(p+14,a);put32(p+18,b);controller_receive(c,p,sizeof(p),now);
}
static void init(controller_t *c) {
    count=0;controller_init(c,123,send_message,NULL);
    cmd(c,1,OP_CONFIGURE,3,100,0);cmd(c,2,OP_START,0,0,0);
}
static void ack(controller_t *c,int64_t now) {
    uint8_t p[17]={MSG_PART_ACK};memcpy(p+1,c->part+1,16);
    controller_receive(c,p,sizeof(p),now);
}
int main(void) {
    controller_t c;init(&c);
    assert(messages[0][9]==PH_DELIVERY && messages[1][9]==PH_ACCEPTANCE && messages[2][9]==PH_COMPLETION);
    controller_tick(&c,100000);assert(c.production.produced_parts==1 && c.pending);
    cmd(&c,2,OP_START,0,0,110000); /* lost reply / duplicate START */
    assert(c.production.produced_parts==1);
    cmd(&c,2,OP_STOP,0,0,110000); /* same ID, different content */
    assert(c.production.state==PROD_RUNNING && messages[count-1][10]==RES_CONFLICT);
    controller_tick(&c,200000);assert(c.production.produced_parts==1);
    ack(&c,200000);controller_tick(&c,200000);assert(c.production.produced_parts==2);
    ack(&c,300000);controller_tick(&c,300000);assert(c.production.produced_parts==3);
    assert(c.part[21]==1 && c.production.state==PROD_IDLE);
    ack(&c,300001);cmd(&c,3,OP_START,0,0,300002);
    assert(c.last_result==RES_STATE); /* needs fresh CONFIGURE */
    cmd(&c,1,OP_CONFIGURE,3,100,300003);assert(messages[count-1][10]==RES_STALE);

    init(&c);cmd(&c,3,OP_PAUSE,0,0,50000);controller_tick(&c,200000);
    assert(c.production.produced_parts==0);
    cmd(&c,4,OP_RESUME,0,0,200000);controller_tick(&c,300000);
    assert(c.production.produced_parts==1);
    cmd(&c,5,OP_STOP,0,0,300001);assert(!c.pending && c.production.state==PROD_IDLE);

    init(&c);controller_tick(&c,100000);
    uint8_t original[22];memcpy(original,c.part,22);
    controller_tick(&c,600000);controller_tick(&c,1100000);controller_tick(&c,1600000);
    assert(c.attempts==4 && memcmp(original,c.part,22)==0);
    controller_tick(&c,2100000);assert(c.production.state==PROD_FAULT && c.production.produced_parts==1);
    cmd(&c,3,OP_STOP,0,0,2100001);assert(c.production.state==PROD_IDLE);

    init(&c);controller_tick(&c,3000001);assert(c.production.state==PROD_FAULT);
    count=0;controller_init(&c,123,send_message,NULL);
    cmd(&c,1,OP_CONFIGURE,3,0,0);assert(c.last_result==RES_INVALID);
    assert(c.production.state==PROD_IDLE);
    uint8_t stale[5]={MSG_HEARTBEAT,0,0,0,122};
    controller_receive(&c,stale,5,99999);assert(c.heartbeat_us==0);
    puts("PASS: controller lifecycle, IDs, retries, backpressure, validation, heartbeat and fault");
    return 0;
}
