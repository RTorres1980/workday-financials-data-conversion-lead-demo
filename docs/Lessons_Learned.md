# Lessons Learned

Points from running the mock conversions that carry over to real implementations.

- **Hold records back instead of defaulting them.** Sending an unmapped account to a suspense account makes the load file balance but hides the problem. Holding the lines back keeps the reconciliation honest: the difference equals what's missing.
- **Reconcile at a level owners recognize.** A single "total debits match" check passes even when revenue lands in the wrong account. Reconciling by company and account type points straight to which mapping is wrong.
- **Departments go stale before accounts do.** In mock 1 every gap in the trial balance came from an inactive department (900) or a catch-all account (6900). Ask for a list of inactive segments before building the mappings.
- **Normalize before you deduplicate.** The duplicate suppliers differed only in case and trailing spaces. A name-plus-tax-ID key on a normalized name catches them, while an exact match does not.
- **Fix data at the source.** Missing tax IDs are corrected in Concur by AP, then re-extracted. Patching them in the conversion files means they come back wrong in the next mock.
- **Make the validation log a generated file.** Writing it from each run means the log always matches the data, and the change history shows how the results improved from one mock to the next.
