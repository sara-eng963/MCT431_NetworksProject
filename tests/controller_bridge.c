/* Host integration bridge: exposes the actual firmware controller to Python. */
#include "controller.h"
#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif
static controller_t controller;
EXPORT void bridge_init(controller_send_fn send) {
    controller_init(&controller,123,send,NULL);
}
EXPORT void bridge_receive(const uint8_t *p,size_t n,int64_t now) {
    controller_receive(&controller,p,n,now);
}
EXPORT void bridge_tick(int64_t now) { controller_tick(&controller,now); }
