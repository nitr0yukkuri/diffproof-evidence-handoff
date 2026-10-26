pub fn greeting(name: &str) -> String {
    format!("Hello, {name}")
}

#[cfg(test)]
mod tests {
    use super::greeting;

    #[test]
    fn formats_a_greeting() {
        assert_eq!(greeting("agent"), "Hello, agent");
    }
}
