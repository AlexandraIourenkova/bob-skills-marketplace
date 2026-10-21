      *  Customer master record; :PFX: is replaced by the includer.
       01  :PFX:-CUSTOMER.
           05  :PFX:-CUST-ID       PIC X(8).
           05  :PFX:-NAME          PIC X(30).
           05  :PFX:-BALANCE       PIC S9(9)V99 COMP-3.
           05  :PFX:-STATUS        PIC X.
               88  :PFX:-ACTIVE           VALUE 'A'.
