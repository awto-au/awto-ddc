// Console line wrap, the decision only: no OSD / SDK calls, so scripts/con_wrap_host.py compiles this file on the host and tests it.
// The caller (console.c AwtoConWrapLine) draws the rows and runs the second composition pass.

// Where a full log row breaks. pcRow = the composed row (time column first, text from ucTxt0), ucLen = its length.
// Returns the characters to draw on the first row. *pucDrop = characters the second pass skips of the same text:
//   last space after the text column: break there, the space is dropped too (draw = drop = index of that space);
//   no space: break at the row edge (draw the whole row, drop ucLen - 1; the row's last cell is the first of the continuation's text).
unsigned char AwtoConWrapBreak(const __xdata char *pcRow, unsigned char ucLen, unsigned char ucTxt0, unsigned char *pucDrop)
{
    unsigned char ucI = ucLen;

    while((--ucI > ucTxt0) && (pcRow[ucI] != ' '))
    {
    }
    if(ucI <= ucTxt0)
    {
        *pucDrop = ucLen - 1;
        return ucLen;
    }
    *pucDrop = ucI;
    return ucI;
}
