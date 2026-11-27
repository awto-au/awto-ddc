	.module ovl
	.globl __xovl
	.globl __dovl
	.area XSEG (XDATA)
__xovl::
	.ds 0x40
	.area DSEG (DATA)
__dovl::
	.ds 0x10
	.area CSEG (CODE)
_main::
	lcall	_f
	ret
