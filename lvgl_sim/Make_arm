#
# Makefile
#
CC 				= arm-linux-gcc
LVGL_DIR_NAME 	?= lvgl
LVGL_DIR 		?= .

CFLAGS 			?= -O3 -g0 -I$(LVGL_DIR)/   -I./freetype_tmp/include/freetype2

LDFLAGS 		?= -lm   -L./freetype_tmp/lib -lfreetype

BIN 			= main
BUILD_DIR 		= ./build
BUILD_OBJ_DIR 	= $(BUILD_DIR)/obj
BUILD_BIN_DIR 	= $(BUILD_DIR)/bin

prefix 			?= /usr
bindir 			?= $(prefix)/bin

#Collect the files to compile
MAINSRC          = ./main.c  ./dict.c

CSRCS += $(shell find ./ui -type f -name '*.c')

include $(LVGL_DIR)/lvgl/lvgl.mk

CSRCS 			+=$(LVGL_DIR)/mouse_cursor_icon.c 

OBJEXT 			?= .o

AOBJS 			= $(ASRCS:.S=$(OBJEXT))
COBJS 			= $(CSRCS:.c=$(OBJEXT))

MAINOBJ 		= $(MAINSRC:.c=$(OBJEXT))

SRCS 			= $(ASRCS) $(CSRCS) $(MAINSRC)
OBJS 			= $(AOBJS) $(COBJS) $(MAINOBJ)
TARGET 			= $(addprefix $(BUILD_OBJ_DIR)/, $(patsubst ./%, %, $(OBJS)))

## MAINOBJ -> OBJFILES


all: default

$(BUILD_OBJ_DIR)/%.o: %.c
	@mkdir -p $(dir $@)
	@$(CC)  $(CFLAGS) -c $< -o $@
	@echo "CC $<"

$(BUILD_OBJ_DIR)/%.o: %.S
	@mkdir -p $(dir $@)
	@$(CC)  $(CFLAGS) -c $< -o $@
	@echo "CC $<"


default: $(TARGET)
	@mkdir -p $(dir $(BUILD_BIN_DIR)/)
	$(CC) -o $(BUILD_BIN_DIR)/$(BIN) $(TARGET) $(LDFLAGS)

clean: 
	rm -rf $(BUILD_DIR)

install:
	install -d $(DESTDIR)$(bindir)
	install $(BUILD_BIN_DIR)/$(BIN) $(DESTDIR)$(bindir)

uninstall:
	$(RM) -r $(addprefix $(DESTDIR)$(bindir)/,$(BIN))

send:
	scp  ./build/bin/main   root@192.168.7.3:/
