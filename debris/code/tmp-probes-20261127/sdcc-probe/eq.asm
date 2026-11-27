	.module eq
	.globl __xovl
	.globl __dovl
	.area CSEG (CODE)
_f::
	mov	dptr,#(__xovl + 0x12)
	movx	a,@dptr
	mov	dptr,#((__xovl + 0x12) + 1)
	movx	@dptr,a
	mov	(__dovl + 0x03),a
	mov	r7,(__dovl + 0x03)
	ret
