#include "controller.h"
#include <string.h>
static uint32_t get32(const uint8_t *p) {
    return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];
}
static void put32(uint8_t *p, uint32_t n) {
    p[0]=(uint8_t)(n>>24); p[1]=(uint8_t)(n>>16);
    p[2]=(uint8_t)(n>>8); p[3]=(uint8_t)n;
}
static void put64(uint8_t *p, uint64_t n) {
    put32(p, (uint32_t)(n>>32)); put32(p+4, (uint32_t)n);
}
static void event(controller_t *c, uint32_t id, uint8_t phase,
                  uint8_t result, uint8_t state) {
    uint8_t p[12]={MSG_COMMAND_EVENT};
    put32(p+1,c->boot_id); put32(p+5,id);
    p[9]=phase; p[10]=result; p[11]=state;
    c->send(p,sizeof(p),c->send_context);
}
static void status(controller_t *c) {
    uint8_t p[STATUS_SIZE]={MSG_STATUS};
    p[1]=(uint8_t)c->production.state;
    put32(p+2,c->boot_id); put32(p+6,c->batch_id);
    put32(p+10,c->production.produced_parts); put32(p+14,c->last_cmd_id);
    c->send(p,sizeof(p),c->send_context);
}
void controller_init(controller_t *c, uint32_t boot,
                     controller_send_fn send, void *context) {
    memset(c,0,sizeof(*c)); production_init(&c->production);
    c->boot_id=boot; c->send=send; c->send_context=context;
}
void controller_receive(controller_t *c, const uint8_t *p, size_t len, int64_t now) {
    if (!p || len<5 || get32(p+1)!=c->boot_id) return;
    if (p[0]==MSG_HEARTBEAT && len==5) { c->heartbeat_us=now; return; }
    if (p[0]==MSG_PART_ACK && len==17) {
        if (c->pending && memcmp(p+1,c->part+1,16)==0) c->pending=false;
        return;
    }
    if (p[0]!=MSG_COMMAND || len<9) return;
    uint32_t id=get32(p+5);
    uint8_t state=(uint8_t)c->production.state;
    event(c,id,PH_DELIVERY,RES_OK,state);
    if (len!=COMMAND_SIZE || id==0) {
        event(c,id,PH_ACCEPTANCE,RES_INVALID,state); return;
    }
    if (c->have_command && id==c->last_cmd_id) {
        if (memcmp(p,c->last_command,COMMAND_SIZE)!=0) {
            event(c,id,PH_ACCEPTANCE,RES_CONFLICT,state); return;
        }
        event(c,id,PH_ACCEPTANCE,c->last_result,c->last_state);
        if (c->last_result==RES_OK) event(c,id,PH_COMPLETION,RES_OK,c->last_state);
        return;
    }
    if (id<=c->last_cmd_id) { event(c,id,PH_ACCEPTANCE,RES_STALE,state); return; }
    uint32_t batch=get32(p+9), arg0=get32(p+14), arg1=get32(p+18);
    uint8_t op=p[13], result=RES_OK;
    if (op<OP_CONFIGURE || op>OP_STOP || !batch) result=RES_INVALID;
    else if (op==OP_CONFIGURE) {
        if (!arg0 || arg1<10 || arg1>3600000) result=RES_INVALID;
        else if (state!=PROD_IDLE || c->pending) result=RES_STATE;
    } else if (batch!=c->batch_id) result=RES_STALE;
    else if (arg0 || arg1) result=RES_INVALID;
    else if (op==OP_START && (state!=PROD_IDLE || c->pending ||
                             !c->production.config.target_parts)) result=RES_STATE;
    else if (op==OP_PAUSE && state!=PROD_RUNNING) result=RES_STATE;
    else if (op==OP_RESUME && state!=PROD_PAUSED) result=RES_STATE;
    c->have_command=true; c->last_cmd_id=id;
    memcpy(c->last_command,p,COMMAND_SIZE); c->last_result=result; c->last_state=state;
    event(c,id,PH_ACCEPTANCE,result,state);
    if (result!=RES_OK) return;
    switch (op) {
    case OP_CONFIGURE:
        (void)production_configure(&c->production,(production_config_t){arg0,arg1});
        c->batch_id=batch; c->production.produced_parts=0; break;
    case OP_START: (void)production_start(&c->production,now); c->heartbeat_us=now; break;
    case OP_PAUSE: (void)production_pause(&c->production); break;
    case OP_RESUME: (void)production_resume(&c->production,now); c->heartbeat_us=now; break;
    case OP_STOP:
        /* Explicit abort: the gateway records this batch as aborted. */
        c->production.state=PROD_IDLE; c->production.next_deadline_us=0;
        c->production.config.target_parts=0; c->pending=false; break;
    }
    c->last_state=(uint8_t)c->production.state;
    event(c,id,PH_COMPLETION,RES_OK,c->last_state); status(c);
}
void controller_tick(controller_t *c, int64_t now) {
    if ((c->production.state==PROD_RUNNING || c->production.state==PROD_PAUSED || c->pending)
        && now-c->heartbeat_us>3000000) c->production.state=PROD_FAULT;
    if (c->pending && c->production.state!=PROD_FAULT && now>=c->retry_us) {
        if (c->attempts>=4) c->production.state=PROD_FAULT;
        else {
            c->send(c->part,PART_SIZE,c->send_context); c->attempts++;
            c->retry_us=now+500000;
        }
    }
    production_event_t produced;
    if (!c->pending && production_update(&c->production,now,&produced)) {
        c->part[0]=MSG_PART; put32(c->part+1,c->boot_id); put32(c->part+5,c->batch_id);
        put64(c->part+9,produced.part_id); put32(c->part+17,produced.produced_count);
        c->part[21]=produced.batch_production_finished;
        if (produced.batch_production_finished) c->production.config.target_parts=0;
        c->pending=true; c->attempts=1; c->retry_us=now+500000;
        c->send(c->part,PART_SIZE,c->send_context);
    }
    if (now>=c->status_us) { status(c); c->status_us=now+1000000; }
}
