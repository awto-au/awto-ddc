// SPDX-License-Identifier: GPL-2.0
// Sets the i915 GMBUS DDC clock for one adapter (#12). i915 hardcodes 100 kHz
// in bus->reg0 and rewrites GMBUS0 from it every transfer; unload restores it.
#include <linux/module.h>
#include <linux/i2c.h>
#include <linux/string.h>

// reg0 offset in struct intel_gmbus (pahole -C intel_gmbus /sys/kernel/btf/i915): 1100.
// adapter is the first member (size 1096), so the bus pointer == the adapter.
#define GMBUS_REG0_OFF		1100
#define GMBUS_ADAPTER_SIZE	1096
#define GMBUS_RATE_MASK		0x700u
#define GMBUS_PIN_MASK		0x01fu

static int adapter = 11;
static int rate = 400;
module_param(adapter, int, 0444);
MODULE_PARM_DESC(adapter, "i2c bus number of an i915 gmbus adapter");
module_param(rate, int, 0444);
MODULE_PARM_DESC(rate, "kHz: 50, 100, 400 or 1000");

static struct i2c_adapter *ad;
static u32 old_reg0;

static u32 *reg0_ptr(void)
{
	return (u32 *)((char *)ad + GMBUS_REG0_OFF);
}

// Read-only live view in /sys/module/gmbus_rate/parameters/reg0.
static int reg0_get(char *buf, const struct kernel_param *kp)
{
	return ad ? sysfs_emit(buf, "0x%x\n", *reg0_ptr()) : sysfs_emit(buf, "none\n");
}
static const struct kernel_param_ops reg0_ops = { .get = reg0_get };
module_param_cb(reg0, &reg0_ops, NULL, 0444);

static int rate_code(int khz)
{
	switch (khz) {
	case 100: return 0;
	case 50: return 1;
	case 400: return 2;
	case 1000: return 3;
	}
	return -1;
}

static int __init gmbus_rate_init(void)
{
	int code = rate_code(rate);
	u32 new;

	if (code < 0) {
		pr_err("gmbus_rate: rate %d invalid (50|100|400|1000)\n", rate);
		return -EINVAL;
	}
	BUILD_BUG_ON(sizeof(struct i2c_adapter) != GMBUS_ADAPTER_SIZE);

	ad = i2c_get_adapter(adapter);
	if (!ad) {
		pr_err("gmbus_rate: no i2c-%d\n", adapter);
		return -ENODEV;
	}
	if (!strstr(ad->name, "gmbus")) {
		pr_err("gmbus_rate: i2c-%d is '%s', not gmbus: refusing\n", adapter, ad->name);
		goto bad;
	}

	i2c_lock_bus(ad, I2C_LOCK_ROOT_ADAPTER);
	old_reg0 = *reg0_ptr();
	// Bits outside pin[4:0] and rate[10:8] must be zero in reg0.
	if ((old_reg0 & ~(GMBUS_PIN_MASK | GMBUS_RATE_MASK)) ||
	    !(old_reg0 & GMBUS_PIN_MASK) || ((old_reg0 >> 8) & 7) > 3) {
		i2c_unlock_bus(ad, I2C_LOCK_ROOT_ADAPTER);
		pr_err("gmbus_rate: reg0 0x%x on '%s' looks wrong: refusing\n", old_reg0, ad->name);
		goto bad;
	}
	new = (old_reg0 & ~GMBUS_RATE_MASK) | ((u32)code << 8);
	*reg0_ptr() = new;
	i2c_unlock_bus(ad, I2C_LOCK_ROOT_ADAPTER);
	pr_info("gmbus_rate: '%s' reg0 0x%x -> 0x%x (%d kHz)\n", ad->name, old_reg0, new, rate);
	return 0;
bad:
	i2c_put_adapter(ad);
	ad = NULL;
	return -EINVAL;
}

static void __exit gmbus_rate_exit(void)
{
	i2c_lock_bus(ad, I2C_LOCK_ROOT_ADAPTER);
	*reg0_ptr() = old_reg0;
	i2c_unlock_bus(ad, I2C_LOCK_ROOT_ADAPTER);
	pr_info("gmbus_rate: '%s' reg0 restored to 0x%x\n", ad->name, old_reg0);
	i2c_put_adapter(ad);
}

module_init(gmbus_rate_init);
module_exit(gmbus_rate_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Set i915 GMBUS DDC clock rate");
