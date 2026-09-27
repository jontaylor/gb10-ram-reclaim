obj-m += gb10_reclaim_right.o
all:
	$(MAKE) -C /lib/modules/$(shell uname -r)/build M=$(CURDIR) KBUILD_MODPOST_WARN=1 modules
