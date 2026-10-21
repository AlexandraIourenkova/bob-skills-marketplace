/* ORDUTIL: routines that ORDLOAD takes in with the compiler's include */
/* directive. Synthetic test data for zos-app-insight, Apache-2.0.     */
fmt_amount: procedure
  parse arg amount
  return format(amount, 9, 2)
