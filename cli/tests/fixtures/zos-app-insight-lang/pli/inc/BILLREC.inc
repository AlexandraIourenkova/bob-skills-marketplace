 /* BILLREC: order record. Original test fixture, Apache-2.0.        */
   DCL 1 ORDER_REC,
         2 ORD_ID       CHAR(10),
         2 ORD_CUST     CHAR(8),
         2 ORD_TYPE     CHAR(1),
         2 ORD_COUNT    FIXED BIN(15),
         2 ORD_QTY(5)   FIXED BIN(31),
         2 ORD_AMT      FIXED DEC(11,2);
