>>SOURCE FORMAT FREE
*> Copyright (c) 2026 Mirepoix AI. BUSL-1.1; see LICENSE.
*> Synthetic state framing; arithmetic expression attribution in PROVENANCE.md.
identification division.
program-id. STATEFUL-INTEREST.
data division.
working-storage section.
01 wire-line pic x(512).
01 tag-name pic x(16).
01 f1 pic x(128).
01 f2 pic x(128).
01 f3 pic x(128).
01 input-done pic 9 value 0.
01 cursor-n binary-long.
01 hash-text pic x(64).
01 account-count binary-long value 0.
01 accounts.
  02 account-entry occurs 8.
    03 account-id pic x(12).
    03 balance-val pic s9(9)v99 comp-3.
01 accepted-count binary-long value 0.
01 accepted-ids.
  02 accepted-id pic x(12) occurs 32.
01 journal-count binary-long value 0.
01 journal-rows.
  02 journal-row pic x(512) occurs 32.
01 record-id pic x(12).
01 record-account pic x(12).
01 rate-hex pic x(128).
01 rate-text pic x(64).
01 rate-size binary-long.
01 start-n binary-long.
01 whole-size binary-long.
01 decimal-pos binary-long.
01 rate-val pic s9(4)v99 comp-3.
01 wide-val pic s9(15)v9(8) comp-3.
01 interest-val pic s9(15)v99 comp-3.
01 closing-val pic s9(15)v99 comp-3.
01 disposition pic x(12) value 'REJECTED'.
01 reason-text pic x(24) value '~'.
01 opening-text pic x(20) value '~'.
01 interest-text pic x(20) value '~'.
01 closing-text pic x(20) value '~'.
01 selected binary-long value 0.
01 duplicate-found pic 9 value 0.
01 i binary-long.
01 j binary-long.
01 hex-table pic x(16) value '0123456789ABCDEF'.
01 hex-char pic x.
01 high-n binary-long.
01 low-n binary-long.
01 byte-n binary-long.
01 format-val pic s9(15)v99 comp-3.
01 format-mag pic 9(15)v99.
01 format-edit pic z(14)9.99.
01 format-text pic x(20).
01 cursor-edit pic zz9.
procedure division.
main.
 perform until input-done = 1
   accept wire-line
   move spaces to tag-name f1 f2 f3
   unstring wire-line delimited by '|' into tag-name f1 f2 f3 end-unstring
   evaluate function trim(tag-name)
    when 'STATE'
      compute cursor-n = function numval(f1)
      move f2 to hash-text
    when 'ACCOUNT'
      add 1 to account-count
      if account-count > 8 perform protocol-error end-if
      move f1 to account-id(account-count)
      compute balance-val(account-count) = function numval(f2)
    when 'ACCEPTED'
      add 1 to accepted-count
      if accepted-count > 32 perform protocol-error end-if
      move f1 to accepted-id(accepted-count)
    when 'JOURNAL'
      add 1 to journal-count
      if journal-count > 32 perform protocol-error end-if
      move wire-line to journal-row(journal-count)
    when 'RECORD'
      move f1 to record-id
      move f2 to record-account
      move f3 to rate-hex
    when 'END' move 1 to input-done
    when other perform protocol-error
   end-evaluate
 end-perform
 if cursor-n < 0 or cursor-n >= 32 or journal-count not = cursor-n
   perform protocol-error
 end-if
 perform varying i from 1 by 1 until i > accepted-count
   if accepted-id(i) = record-id move 1 to duplicate-found end-if
 end-perform
 perform varying i from 1 by 1 until i > account-count
   if account-id(i) = record-account move i to selected end-if
 end-perform
 evaluate true
  when duplicate-found = 1
   move 'DUPLICATE' to disposition
   move 'ACCEPTED_ID' to reason-text
  when selected = 0
   move 'UNKNOWN_ACCOUNT' to reason-text
  when other
   move balance-val(selected) to format-val
   perform format-amount
   move format-text to opening-text closing-text
   perform decode-rate
   perform calculate-record
 end-evaluate
 compute cursor-edit = cursor-n + 1
 display 'STATE|' function trim(cursor-edit) '|' hash-text
 perform varying i from 1 by 1 until i > account-count
   move balance-val(i) to format-val
   perform format-amount
   display 'ACCOUNT|' function trim(account-id(i)) '|' function trim(format-text)
 end-perform
 perform varying i from 1 by 1 until i > accepted-count
   display 'ACCEPTED|' function trim(accepted-id(i))
 end-perform
 perform varying i from 1 by 1 until i > journal-count
   display function trim(journal-row(i))
 end-perform
 move cursor-n to cursor-edit
 display 'JOURNAL|' function trim(cursor-edit) '|' function trim(record-id)
   '|' function trim(record-account) '|' function trim(rate-hex)
   '|' function trim(disposition) '|' function trim(reason-text)
   '|' function trim(opening-text) '|' function trim(interest-text)
   '|' function trim(closing-text)
 display 'END'
 move 0 to return-code
 goback.
decode-rate.
 move spaces to rate-text
 compute rate-size = function length(function trim(rate-hex))
 perform varying j from 1 by 2 until j > rate-size
   move rate-hex(j:1) to hex-char
   move 0 to high-n
   inspect hex-table tallying high-n for characters before initial hex-char
   move rate-hex(j + 1:1) to hex-char
   move 0 to low-n
   inspect hex-table tallying low-n for characters before initial hex-char
   if high-n > 15 or low-n > 15 perform protocol-error end-if
   compute byte-n = high-n * 16 + low-n + 1
   compute start-n = (j + 1) / 2
   move function char(byte-n) to rate-text(start-n:1)
 end-perform
 move function trim(rate-text) to rate-text
 compute rate-size = function length(function trim(rate-text)).
calculate-record.
 move 1 to start-n
 if rate-text(1:1) = '+' or rate-text(1:1) = '-'
   move 2 to start-n
 end-if
 compute whole-size = rate-size - start-n - 2
 if whole-size < 1
   move 'INVALID_INPUT' to reason-text
   exit paragraph
 end-if
 if whole-size > 4
   move 'RATE_OVERFLOW' to reason-text
   exit paragraph
 end-if
 compute decimal-pos = rate-size - 2
 if rate-text(decimal-pos:1) not = '.' or
   rate-text(start-n:whole-size) is not numeric or
   rate-text(decimal-pos + 1:2) is not numeric
   move 'INVALID_INPUT' to reason-text
   exit paragraph
 end-if
 compute rate-val = function numval(rate-text)
 *> Bounded public CardDemo expression; no ROUNDED phrase.
 compute wide-val = balance-val(selected) * rate-val / 1200
 move wide-val to interest-val
 if interest-val > 999999999.99 or interest-val < -999999999.99
   move 'INTEREST_OVERFLOW' to reason-text
   exit paragraph
 end-if
 move interest-val to format-val
 perform format-amount
 move format-text to interest-text
 compute closing-val = balance-val(selected) + interest-val
 if closing-val > 999999999.99 or closing-val < -999999999.99
   move 'BALANCE_OVERFLOW' to reason-text
   exit paragraph
 end-if
 move closing-val to balance-val(selected) format-val
 perform format-amount
 move format-text to closing-text
 move 'APPLIED' to disposition
 add 1 to accepted-count
 move record-id to accepted-id(accepted-count).
format-amount.
 compute format-mag = function abs(format-val)
 move format-mag to format-edit
 move spaces to format-text
 if format-val < 0
   string '-' function trim(format-edit) into format-text end-string
 else
   move function trim(format-edit) to format-text
 end-if.
protocol-error.
 display 'invalid transition protocol' upon syserr
 move 1 to return-code
 stop run.
