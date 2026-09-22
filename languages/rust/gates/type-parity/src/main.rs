//! The `rust` arm of the type-parity gate.
//!
//! The `typescript` / `python` twins, same shape: reach each cell's `*_type_entities()`
//! across the crate boundary, print one JSON line carrying, per type entity, the peer's
//! own content hash and a normalisation of the entity's data tree.
//!
//! ## Why the JSON is hand-written
//!
//! There is no serde in this arm's dependency set and there should not be: the profile's
//! `[deps]` block says this target adds NOTHING beyond what the peer already pulls, and
//! `--network=none` builds from keystone's vendor mirror. `chunking-parity`'s rust arm
//! makes the same call with a `format!`. What is different here is that this arm emits a
//! *recursive* structure rather than eight scalars, so the escaping is real code — see
//! `push_json_string`, which is the one place this file could be silently wrong.
//!
//! ## The one thing this arm must not do
//!
//! Fall through on a `Value` variant it does not handle. `compare.py` cross-checks the
//! normalised data against the peer's content hash precisely because each arm's
//! normaliser is per-port code that nothing else validates; a variant quietly rendered as
//! `null` here would show up as a CONTRADICTION rather than as a divergence blamed on a
//! port, but only because every branch below is explicit. The match is exhaustive by
//! construction — no `_ =>` arm.

use entity_core_protocol::value::{Key, Value};

/// Append a JSON string literal, escaped per RFC 8259.
///
/// Control characters below 0x20 MUST be `\u00XX`-escaped; a raw one produces JSON that
/// `json.loads` rejects, and the arm would fail loudly rather than silently — but the two
/// specials that would fail QUIETLY are `"` and `\`, which is why they come first.
fn push_json_string(out: &mut String, s: &str) {
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// The ECF `Value` tree -> canonical JSON, matching the other two arms exactly.
///
/// Map keys are SORTED, deliberately: the codec re-sorts them length-then-lex before
/// hashing, so declaration order provably does not reach the bytes. That is the one
/// distinction all three normalisers drop on purpose, and the content hash is the
/// standing control on whether dropping it was right.
///
/// A non-text map key panics rather than being coerced. The type-entity corpus has only
/// text keys; a byte or integer key appearing here would mean the entity is not the shape
/// this gate believes it is measuring, and stringifying it would hide that.
fn normalise(v: &Value, out: &mut String) {
    match v {
        Value::Null => out.push_str("null"),
        Value::Bool(b) => out.push_str(if *b { "true" } else { "false" }),
        Value::UInt(n) => out.push_str(&n.to_string()),
        // value = -1 - n. Rendered as a JSON number to match `python` and `typescript`.
        Value::NInt(n) => out.push_str(&format!("-{}", (*n as i128) + 1)),
        Value::Float(f) => out.push_str(&format!("{f}")),
        Value::Text(s) => push_json_string(out, s),
        // `{"__bytes__": "<hex>"}` on all three arms. A bare hex string would be
        // indistinguishable from a text field whose value happens to be hex.
        Value::Bytes(b) => {
            out.push_str("{\"__bytes__\":");
            push_json_string(out, &hex(b));
            out.push('}');
        }
        Value::Array(items) => {
            out.push('[');
            for (i, item) in items.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                normalise(item, out);
            }
            out.push(']');
        }
        Value::Map(entries) => {
            let mut pairs: Vec<(&String, &Value)> = entries
                .iter()
                .map(|(k, v)| match k {
                    Key::Text(s) => (s, v),
                    other => panic!(
                        "REFUSING: non-text map key {other:?} in a type entity. Coercing \
                         it would hide that this entity is not the shape the gate believes \
                         it is measuring."
                    ),
                })
                .collect();
            pairs.sort_by(|a, b| a.0.cmp(b.0));
            out.push('{');
            for (i, (k, v)) in pairs.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                push_json_string(out, k);
                out.push(':');
                normalise(v, out);
            }
            out.push('}');
        }
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 2 {
        eprintln!("usage: probe <content|history>");
        std::process::exit(2);
    }
    let ext = args[1].as_str();

    // The one per-extension fact in this arm. Unlike the other two ports, the cells are
    // separate CRATES here, so this is a match rather than a table lookup -- and adding a
    // 27th extension is a dependency plus an arm, which is the same edit the other two
    // arms need in their SUBJECTS map.
    let entities: Vec<(&'static str, entity_core_protocol::peer::model::Entity)> = match ext {
        "content" => entity_content::types::content_type_entities(),
        "history" => entity_history::types::history_type_entities(),
        other => {
            eprintln!("REFUSING: unknown extension {other:?}; expected content|history");
            std::process::exit(2);
        }
    };

    let mut out = String::new();
    out.push_str("{\"port\":\"rust\",\"extension\":");
    push_json_string(&mut out, ext);
    out.push_str(",\"types\":[");
    for (i, (name, entity)) in entities.iter().enumerate() {
        if i > 0 {
            out.push(',');
        }
        out.push_str("{\"name\":");
        push_json_string(&mut out, name);
        out.push_str(",\"hash\":");
        push_json_string(&mut out, &hex(&entity.hash));
        out.push_str(",\"data\":");
        normalise(&entity.data, &mut out);
        out.push('}');
    }
    out.push_str("]}");
    println!("{out}");
}
