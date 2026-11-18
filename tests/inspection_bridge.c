#include "inspection.h"
#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif
static inspection_t station;
EXPORT void bridge_init(inspection_send_fn send) { inspection_init(&station,456,send,NULL); }
EXPORT void bridge_receive(const uint8_t *p,size_t n,int64_t now) { inspection_receive(&station,p,n,now); }
EXPORT void bridge_tick(int64_t now) { inspection_tick(&station,now); }
EXPORT void bridge_disconnect(void) { inspection_disconnect(&station); }
