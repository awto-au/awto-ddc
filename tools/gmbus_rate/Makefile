KDIR ?= /usr/src/kernels/$(shell uname -r)
obj-m := gmbus_rate.o
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) modules
clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
