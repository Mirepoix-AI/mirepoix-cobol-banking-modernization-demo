// Copyright (c) 2026 Mirepoix AI.
// Licensed under the Business Source License 1.1 (BUSL-1.1). See LICENSE file in this package.
// Change Date: 2030-06-02. Change License: Apache License, Version 2.0.
// Portable Rust counterpart for the bounded Apache-2.0 CardDemo monthly-interest rule.

use std::env;
use std::process::ExitCode;

const MONTHLY_DIVISOR: i128 = 120_000;
const MAX_OUTPUT_CENTS: i128 = 99_999_999_999;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum InputError {
    Invalid,
    Overflow,
}

fn parse_fixed(input: &str, maximum_integral_digits: usize) -> Result<i128, InputError> {
    let (negative, unsigned) = match input.as_bytes().first() {
        Some(b'-') => (true, &input[1..]),
        Some(b'+') => (false, &input[1..]),
        _ => (false, input),
    };
    let (integral, fractional) = match unsigned.split_once('.') {
        Some(parts) => parts,
        None => return Err(InputError::Invalid),
    };
    if integral.is_empty()
        || integral.len() > maximum_integral_digits
        || fractional.len() != 2
        || !integral.bytes().all(|byte| byte.is_ascii_digit())
        || !fractional.bytes().all(|byte| byte.is_ascii_digit())
    {
        return if integral.len() > maximum_integral_digits
            && integral.bytes().all(|byte| byte.is_ascii_digit())
            && fractional.len() == 2
            && fractional.bytes().all(|byte| byte.is_ascii_digit())
        {
            Err(InputError::Overflow)
        } else {
            Err(InputError::Invalid)
        };
    }
    let whole = integral.parse::<i128>().map_err(|_| InputError::Overflow)?;
    let fraction = fractional
        .parse::<i128>()
        .map_err(|_| InputError::Overflow)?;
    let scaled = whole
        .checked_mul(100)
        .and_then(|value| value.checked_add(fraction))
        .ok_or(InputError::Overflow)?;
    Ok(if negative { -scaled } else { scaled })
}

fn format_cents(cents: i128) -> String {
    let sign = if cents < 0 { "-" } else { "" };
    let magnitude = cents.abs();
    format!("{sign}{}.{:02}", magnitude / 100, magnitude % 100)
}

fn calculate(balance: &str, rate: &str) -> Result<i128, InputError> {
    let balance_cents = parse_fixed(balance, 9)?;
    let rate_hundredths = parse_fixed(rate, 4)?;
    let product = balance_cents
        .checked_mul(rate_hundredths)
        .ok_or(InputError::Overflow)?;
    // Signed integer division truncates toward zero, matching COBOL assignment
    // to PIC S9(09)V99 without a ROUNDED phrase.
    let monthly_cents = product / MONTHLY_DIVISOR;
    if monthly_cents.abs() > MAX_OUTPUT_CENTS {
        return Err(InputError::Overflow);
    }

    // Deliberately wrong build used only to prove that the harness detects drift.
    #[cfg(carddemo_mutation)]
    let monthly_cents = if monthly_cents < MAX_OUTPUT_CENTS {
        monthly_cents + 1
    } else {
        monthly_cents - 1
    };

    Ok(monthly_cents)
}

fn main() -> ExitCode {
    let arguments: Vec<String> = env::args().skip(1).collect();
    if arguments.len() != 2 {
        println!("ERROR\tINVALID_INPUT");
        return ExitCode::from(2);
    }

    match calculate(&arguments[0], &arguments[1]) {
        Ok(cents) => {
            println!("OK\t{}", format_cents(cents));
            ExitCode::SUCCESS
        }
        Err(InputError::Invalid) => {
            println!("ERROR\tINVALID_INPUT");
            ExitCode::from(2)
        }
        Err(InputError::Overflow) => {
            println!("ERROR\tOVERFLOW");
            ExitCode::from(3)
        }
    }
}
