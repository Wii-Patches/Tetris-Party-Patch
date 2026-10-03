SECTIONS
{
    . = 0;
    .text : {
        *(.gcstart)
        *(.text .text.*)
        *(.rodata .rodata.*)
        *(.gctail)
    }
}
