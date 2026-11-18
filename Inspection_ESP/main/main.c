#include "inspection.h"
#include <errno.h>
#include <string.h>
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include "driver/uart.h"
#include "esp_err.h"
#include "esp_timer.h"
#include "esp_random.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "cJSON.h"
#include "lwip/sockets.h"
#include "lwip/tcp.h"

#define TCP_PORT 9000
#define WIFI_READY BIT0
static EventGroupHandle_t wifi_events;
static inspection_t station;
static int client=-1;
static bool socket_failed;

static uint32_t trace32(const uint8_t *p) {
    return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];
}

static void serial_line(const char *line) {
    uart_write_bytes(UART_NUM_0,line,strlen(line));
    uart_write_bytes(UART_NUM_0,"\n",1);
}
static void provision(wifi_config_t *config) {
    nvs_handle_t storage;
    ESP_ERROR_CHECK(nvs_open("inspection",NVS_READWRITE,&storage));
    size_t ssid_len=sizeof(config->sta.ssid),pass_len=sizeof(config->sta.password);
    esp_err_t ssid_result=nvs_get_str(storage,"ssid",(char *)config->sta.ssid,&ssid_len);
    esp_err_t pass_result=nvs_get_str(storage,"password",(char *)config->sta.password,&pass_len);
    if (ssid_result==ESP_OK && pass_result==ESP_OK && config->sta.ssid[0]) {
        nvs_close(storage);return;
    }
    memset(config,0,sizeof(*config));
    serial_line("{\"setup_required\":true}");
    char line[256];size_t used=0;bool discard=false;
    while (1) {
        uint8_t ch;
        if (uart_read_bytes(UART_NUM_0,&ch,1,pdMS_TO_TICKS(100))!=1) continue;
        if (ch=='\r') continue;
        if (ch!='\n') {
            if (used<sizeof(line)-1 && !discard) line[used++]=(char)ch;
            else discard=true;
            continue;
        }
        line[used]=0;
        cJSON *root=discard?NULL:cJSON_Parse(line);
        const cJSON *ssid=cJSON_GetObjectItemCaseSensitive(root,"ssid");
        const cJSON *password=cJSON_GetObjectItemCaseSensitive(root,"password");
        bool valid=cJSON_IsString(ssid) && cJSON_IsString(password) &&
            strlen(ssid->valuestring)>0 && strlen(ssid->valuestring)<sizeof(config->sta.ssid) &&
            strlen(password->valuestring)<sizeof(config->sta.password);
        if (valid) {
            memcpy(config->sta.ssid,ssid->valuestring,strlen(ssid->valuestring));
            memcpy(config->sta.password,password->valuestring,strlen(password->valuestring));
            ESP_ERROR_CHECK(nvs_set_str(storage,"ssid",ssid->valuestring));
            ESP_ERROR_CHECK(nvs_set_str(storage,"password",password->valuestring));
            ESP_ERROR_CHECK(nvs_commit(storage));
        }
        cJSON_Delete(root);memset(line,0,sizeof(line));used=0;discard=false;
        if (valid) { nvs_close(storage);serial_line("{\"provisioned\":true}");return; }
        serial_line("{\"error\":\"invalid_wifi_configuration\"}");
    }
}
static void network_event(void *arg,esp_event_base_t base,int32_t id,void *data) {
    (void)arg;
    if (base==WIFI_EVENT && id==WIFI_EVENT_STA_START) esp_wifi_connect();
    else if (base==WIFI_EVENT && id==WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(wifi_events,WIFI_READY);
        esp_wifi_connect();
    } else if (base==IP_EVENT && id==IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event=data;
        char line[96];
        snprintf(line,sizeof(line),"{\"ip\":\"" IPSTR "\",\"port\":%d}",IP2STR(&event->ip_info.ip),TCP_PORT);
        serial_line(line);xEventGroupSetBits(wifi_events,WIFI_READY);
    }
}
static bool send_all(const uint8_t *p,size_t length) {
    while (length) {
        int count=send(client,p,length,0);
        if (count<0 && errno==EINTR) continue;
        if (count<=0) return false;
        p+=count;length-=(size_t)count;
    }
    return true;
}
static void send_message(const uint8_t *p,size_t length,void *context) {
    (void)context;
    if (length==20 && p[0]==INS_REPLY && p[9]==INS_COMPLETION && p[11]!=INS_NONE) {
        char line[180];
        uint64_t part=((uint64_t)trace32(p+12)<<32)|trace32(p+16);
        snprintf(line,sizeof(line),"{\"event\":\"inspection_completed\",\"job_id\":%lu,\"part_id\":\"%llu\",\"verdict\":\"%s\"}",
            (unsigned long)trace32(p+5),(unsigned long long)part,p[11]==INS_PASS?"PASS":"FAIL");
        serial_line(line);
    }
    if (client<0 || socket_failed) return;
    uint8_t message[130]={(uint8_t)(length>>8),(uint8_t)length};
    if (length>128) { socket_failed=true;return; }
    memcpy(message+2,p,length);
    if (!send_all(message,length+2)) socket_failed=true;
}
static void session(void) {
    uint8_t prefix[2],payload[128];size_t prefix_used=0,used=0,wanted=0;
    socket_failed=false;station.status_us=0;
    while (!socket_failed && (xEventGroupGetBits(wifi_events)&WIFI_READY)) {
        fd_set read_set;FD_ZERO(&read_set);FD_SET(client,&read_set);
        struct timeval timeout={.tv_sec=0,.tv_usec=10000};
        int ready=select(client+1,&read_set,NULL,NULL,&timeout);
        if (ready<0) break;
        if (ready>0) {
            uint8_t input[128];int count=recv(client,input,sizeof(input),0);
            if (count<=0) break;
            for (int i=0;i<count && !socket_failed;i++) {
                if (prefix_used<2) {
                    prefix[prefix_used++]=input[i];
                    if (prefix_used==2) {
                        wanted=((size_t)prefix[0]<<8)|prefix[1];used=0;
                        if (!wanted || wanted>sizeof(payload)) socket_failed=true;
                    }
                } else {
                    payload[used++]=input[i];
                    if (used==wanted) {
                        if (used==21 && payload[0]==INS_JOB) {
                            char line[180];
                            uint64_t part=((uint64_t)trace32(payload+13)<<32)|trace32(payload+17);
                            snprintf(line,sizeof(line),"{\"event\":\"inspection_request\",\"job_id\":%lu,\"batch_id\":%lu,\"part_id\":\"%llu\"}",
                                (unsigned long)trace32(payload+5),(unsigned long)trace32(payload+9),(unsigned long long)part);
                            serial_line(line);
                        }
                        inspection_receive(&station,payload,used,esp_timer_get_time());
                        prefix_used=0;used=0;
                    }
                }
            }
        }
        inspection_tick(&station,esp_timer_get_time());
    }
    inspection_disconnect(&station);
}
void app_main(void) {
    uart_config_t uart={.baud_rate=115200,.data_bits=UART_DATA_8_BITS,
        .parity=UART_PARITY_DISABLE,.stop_bits=UART_STOP_BITS_1,
        .flow_ctrl=UART_HW_FLOWCTRL_DISABLE,.source_clk=UART_SCLK_DEFAULT};
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM_0,1024,512,0,NULL,0));
    ESP_ERROR_CHECK(uart_param_config(UART_NUM_0,&uart));
    ESP_ERROR_CHECK(uart_set_pin(UART_NUM_0,1,3,UART_PIN_NO_CHANGE,UART_PIN_NO_CHANGE));
    esp_err_t err=nvs_flash_init();
    if (err==ESP_ERR_NVS_NO_FREE_PAGES || err==ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());err=nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);
    wifi_config_t config={0};provision(&config);
    wifi_events=xEventGroupCreate();
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();
    wifi_init_config_t init=WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT,ESP_EVENT_ANY_ID,network_event,NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT,IP_EVENT_STA_GOT_IP,network_event,NULL));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA,&config));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
    uint32_t boot;do { boot=esp_random(); } while (!boot);
    inspection_init(&station,boot,send_message,NULL);
    int server=socket(AF_INET,SOCK_STREAM,IPPROTO_IP);
    if (server<0) { serial_line("{\"error\":\"socket\"}");return; }
    int reuse=1;setsockopt(server,SOL_SOCKET,SO_REUSEADDR,&reuse,sizeof(reuse));
    struct sockaddr_in address={.sin_family=AF_INET,.sin_port=htons(TCP_PORT),.sin_addr.s_addr=htonl(INADDR_ANY)};
    if (bind(server,(struct sockaddr *)&address,sizeof(address))<0 || listen(server,1)<0) {
        serial_line("{\"error\":\"listen\"}");close(server);return;
    }
    while (1) {
        xEventGroupWaitBits(wifi_events,WIFI_READY,pdFALSE,pdTRUE,portMAX_DELAY);
        client=accept(server,NULL,NULL);
        if (client<0) { vTaskDelay(pdMS_TO_TICKS(100));continue; }
        int no_delay=1;
        setsockopt(client,IPPROTO_TCP,TCP_NODELAY,&no_delay,sizeof(no_delay));
        struct timeval send_timeout={.tv_sec=0,.tv_usec=200000};
        setsockopt(client,SOL_SOCKET,SO_SNDTIMEO,&send_timeout,sizeof(send_timeout));
        session();shutdown(client,SHUT_RDWR);close(client);client=-1;
    }
}
