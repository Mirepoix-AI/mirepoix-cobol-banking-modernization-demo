// Copyright (c) 2026 Mirepoix AI. BUSL-1.1; see LICENSE.
// Synthetic transition protocol; not original CardDemo file/runtime semantics.
use std::io::{self, Read};

fn fixed(text: &str) -> i128 {
    let negative = text.starts_with('-');
    let unsigned = text.trim_start_matches('-');
    let parts: Vec<_> = unsigned.split('.').collect();
    let amount = parts[0].parse::<i128>().unwrap()*100 + parts[1].parse::<i128>().unwrap();
    if negative { -amount } else { amount }
}
fn amount(cents: i128) -> String {
    format!("{}{}.{:02}",if cents < 0 {"-"} else {""},cents.abs()/100,cents.abs()%100)
}
fn rate(text: &str) -> Result<i128,&'static str> {
    let text=text.trim_matches(' ');
    let unsigned=text.strip_prefix('-').or_else(||text.strip_prefix('+')).unwrap_or(text);
    if unsigned.len()<4 { return Err("INVALID_INPUT"); }
    if unsigned.len()-3>4 { return Err("RATE_OVERFLOW"); }
    let split=unsigned.len()-3;
    if unsigned.as_bytes()[split]!=b'.' || !unsigned[..split].bytes().all(|b|b.is_ascii_digit()) ||
        !unsigned[split+1..].bytes().all(|b|b.is_ascii_digit()) { return Err("INVALID_INPUT"); }
    let cents=unsigned[..split].parse::<i128>().unwrap()*100+unsigned[split+1..].parse::<i128>().unwrap();
    Ok(if text.starts_with('-') {-cents} else {cents})
}
fn unhex(hex: &str) -> String {
    assert!(hex.len()<=128 && hex.len()%2==0);
    let bytes: Vec<u8>=(0..hex.len()).step_by(2).map(|i|u8::from_str_radix(&hex[i..i+2],16).unwrap()).collect();
    String::from_utf8(bytes).unwrap()
}
fn main() {
    let mut input=String::new(); io::stdin().read_to_string(&mut input).unwrap();
    let mut next=0usize; let mut hash=String::new(); let mut accounts=Vec::<(String,i128)>::new();
    let mut accepted=Vec::<String>::new(); let mut journal=Vec::<String>::new(); let mut record=None;
    for line in input.lines() {
        let fields: Vec<_>=line.split('|').collect();
        match fields[0] {
            "STATE" => {next=fields[1].parse().unwrap();hash=fields[2].to_owned();},
            "ACCOUNT" => accounts.push((fields[1].to_owned(),fixed(fields[2]))),
            "ACCEPTED" => accepted.push(fields[1].to_owned()),
            "JOURNAL" => journal.push(line.to_owned()),
            "RECORD" => record=Some((fields[1].to_owned(),fields[2].to_owned(),fields[3].to_owned())),
            "END" => (), _ => panic!("invalid wire record"),
        }
    }
    assert!(accounts.len()<=8 && next<32 && journal.len()==next && accepted.len()<=32);
    let (id,account,hex)=record.unwrap();
    let mut disposition="REJECTED"; let mut reason="~";
    let mut opening="~".to_owned(); let mut interest="~".to_owned(); let mut closing="~".to_owned();
    if accepted.contains(&id) { disposition="DUPLICATE";reason="ACCEPTED_ID"; }
    else if let Some(index)=accounts.iter().position(|(key,_)|key==&account) {
        let balance=accounts[index].1;
        opening=amount(balance);closing=opening.clone();
        match rate(&unhex(&hex)) {
            Err(error) => reason=error,
            Ok(rate) => {
                let delta=balance*rate/120000;
                if delta.abs()>99_999_999_999 {reason="INTEREST_OVERFLOW";}
                else {
                    interest=amount(delta);
                    if (balance+delta).abs()>99_999_999_999 {reason="BALANCE_OVERFLOW";}
                    else {disposition="APPLIED";accounts[index].1=balance+delta;closing=amount(balance+delta);accepted.push(id.clone());}
                }
            }
        }
    } else {reason="UNKNOWN_ACCOUNT";}
    journal.push(format!("JOURNAL|{next}|{id}|{account}|{hex}|{disposition}|{reason}|{opening}|{interest}|{closing}"));
    println!("STATE|{}|{hash}",next+1);
    for (id,value) in accounts {println!("ACCOUNT|{id}|{}",amount(value));}
    for id in accepted {println!("ACCEPTED|{id}");}
    for row in journal {println!("{row}");}
    println!("END");
}
