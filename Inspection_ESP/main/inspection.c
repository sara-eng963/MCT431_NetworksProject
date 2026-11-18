#include "inspection.h"
#include <string.h>
static uint32_t get32(const uint8_t *p) {
    return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];
}
static uint64_t get64(const uint8_t *p) { return ((uint64_t)get32(p)<<32)|get32(p+4); }
static void put32(uint8_t *p,uint32_t n) {
    p[0]=(uint8_t)(n>>24);p[1]=(uint8_t)(n>>16);p[2]=(uint8_t)(n>>8);p[3]=(uint8_t)n;
}
static void reply(inspection_t *s,uint32_t id,uint8_t phase,uint8_t result,uint8_t verdict,uint64_t part) {
    uint8_t p[20]={INS_REPLY};
    put32(p+1,s->boot_id);put32(p+5,id);p[9]=phase;p[10]=result;p[11]=verdict;
    put32(p+12,(uint32_t)(part>>32));put32(p+16,(uint32_t)part);
    s->send(p,sizeof(p),s->context);
}
static void status(inspection_t *s) {
    uint8_t p[30]={INS_STATUS};
    p[1]=s->state;put32(p+2,s->boot_id);put32(p+6,s->batch_id);
    put32(p+10,s->last_id);put32(p+14,s->inspection_ms);
    put32(p+18,s->rule_n);put32(p+22,s->rule_k);
    /* Reserved tail must stay zero for future protocol versions. */
    s->send(p,sizeof(p),s->context);
}
void inspection_init(inspection_t *s,uint32_t boot,inspection_send_fn send,void *context) {
    memset(s,0,sizeof(*s));s->boot_id=boot;s->send=send;s->context=context;
}
void inspection_disconnect(inspection_t *s) {
    /* Never finish work during an unobserved disconnected session. */
    s->state=INS_FAULT;s->complete=false;
}
void inspection_receive(inspection_t *s,const uint8_t *p,size_t len,int64_t now) {
    if (!p || len<5 || get32(p+1)!=s->boot_id) return;
    if (p[0]==INS_HEARTBEAT && len==5) { s->heartbeat_us=now;return; }
    if (len<9 || (p[0]!=INS_CONFIGURE && p[0]!=INS_JOB && p[0]!=INS_RESET)) return;
    uint32_t id=get32(p+5);
    reply(s,id,INS_DELIVERY,INS_OK,INS_NONE,0);
    size_t expected=p[0]==INS_CONFIGURE?25:(p[0]==INS_JOB?21:9);
    if (len!=expected || !id) { reply(s,id,INS_ACCEPTANCE,INS_INVALID,INS_NONE,0);return; }
    if (s->have_request && id==s->last_id) {
        if (len!=s->last_length || memcmp(p,s->last_request,len)!=0) {
            reply(s,id,INS_ACCEPTANCE,INS_CONFLICT,INS_NONE,0);return;
        }
        if (s->state==INS_FAULT && p[0]==INS_JOB) {
            reply(s,id,INS_ACCEPTANCE,INS_STATE,INS_NONE,s->part_id);return;
        }
        reply(s,id,INS_ACCEPTANCE,s->last_result,INS_NONE,s->part_id);
        if (s->complete) reply(s,id,INS_COMPLETION,s->last_result,s->last_verdict,s->part_id);
        return;
    }
    if (id<=s->last_id) { reply(s,id,INS_ACCEPTANCE,INS_STALE,INS_NONE,0);return; }
    uint8_t result=INS_OK;
    uint32_t batch=p[0]==INS_RESET?0:get32(p+9);
    uint64_t part=p[0]==INS_JOB?get64(p+13):0;
    if (p[0]==INS_RESET) {
        /* Reset explicitly aborts any active job and invalidates configuration. */
    } else if (s->state==INS_FAULT || s->state==INS_BUSY) result=INS_STATE;
    else if (!batch) result=INS_INVALID;
    else if (p[0]==INS_CONFIGURE) {
        uint32_t ms=get32(p+13),n=get32(p+17);
        if (ms<10 || ms>3600000 || !n) result=INS_INVALID;
    } else if (batch!=s->batch_id || !s->rule_n) result=INS_STALE;
    else if (!part) result=INS_INVALID;
    /* A busy receiver cannot replace the active job's retry/completion cache. */
    if (s->state==INS_BUSY && result!=INS_OK) {
        reply(s,id,INS_ACCEPTANCE,result,INS_NONE,part);return;
    }
    s->have_request=true;s->last_id=id;s->last_length=(uint8_t)len;
    memcpy(s->last_request,p,len);s->last_result=result;
    s->part_id=part;s->last_verdict=INS_NONE;s->complete=false;
    reply(s,id,INS_ACCEPTANCE,result,INS_NONE,part);
    if (result!=INS_OK) return;
    s->heartbeat_us=now;
    if (p[0]==INS_CONFIGURE) {
        s->batch_id=batch;s->inspection_ms=get32(p+13);
        s->rule_n=get32(p+17);s->rule_k=get32(p+21);s->complete=true;
    } else if (p[0]==INS_RESET) {
        s->state=INS_IDLE;s->batch_id=0;s->rule_n=0;s->complete=true;
    } else {
        s->state=INS_BUSY;s->completion_us=now+(int64_t)s->inspection_ms*1000;
    }
    if (s->complete) reply(s,id,INS_COMPLETION,INS_OK,INS_NONE,part);
    status(s);
}
void inspection_tick(inspection_t *s,int64_t now) {
    if (s->state==INS_BUSY && now-s->heartbeat_us>3000000) inspection_disconnect(s);
    if (s->state==INS_BUSY && now>=s->completion_us) {
        /* Modulo first avoids overflow when part_id is near UINT64_MAX. */
        uint64_t remainder=(s->part_id%s->rule_n+(uint64_t)s->rule_k%s->rule_n)%s->rule_n;
        s->last_verdict=remainder==0?INS_FAIL:INS_PASS;
        s->complete=true;s->state=INS_IDLE;
        reply(s,s->last_id,INS_COMPLETION,INS_OK,s->last_verdict,s->part_id);
    }
    if (now>=s->status_us) { status(s);s->status_us=now+1000000; }
}
