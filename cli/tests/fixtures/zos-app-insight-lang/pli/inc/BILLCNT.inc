 /* BILLCNT: run counters. Original test fixture, Apache-2.0.        */
   DCL 1 RUN_COUNTS STATIC,
         2 CNT_LINES    FIXED BIN(31) INIT(0),
         2 CNT_SKIPPED  FIXED BIN(31) INIT(0);
   %INCLUDE BILLWS;
