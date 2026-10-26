package greeting

import "testing"

func TestGreeting(t *testing.T) {
	if got := Greeting("agent"); got != "Hello, agent" {
		t.Fatalf("Greeting() = %q", got)
	}
}
