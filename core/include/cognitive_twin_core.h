/*
 * cognitive_twin_core.h — C ABI for the portable Rust core.
 *
 * Link libcognitive_twin_core.a and import this header (via a module map or a
 * bridging header) to call the twin from Swift/Obj-C on iOS and macOS.
 *
 * All functions returning `char *` transfer ownership to the caller — free the
 * result with ctwin_string_free(). Inputs are UTF-8 C strings.
 */
#ifndef COGNITIVE_TWIN_CORE_H
#define COGNITIVE_TWIN_CORE_H

#ifdef __cplusplus
extern "C" {
#endif

/* Compile a persona (JSON) into its system-prompt block. */
char *ctwin_persona_prompt(const char *persona_json);

/* Route a prompt against a policy (JSON). Returns a JSON decision:
 * {"model","model_key","rule_id","complexity","risk"}. device_state may be "". */
char *ctwin_route(const char *policy_json, const char *prompt, const char *device_state);

/* Build the full system prompt: base + persona + memory summary.
 * recent_prompts_json is a JSON array of strings. */
char *ctwin_system_prompt(const char *base, const char *persona_json,
                          const char *recent_prompts_json);

/* Run one full agent turn against a local Ollama model and return the answer.
 * recent_prompts_json is a JSON array of strings. The single call an app needs. */
char *ctwin_ask(const char *model, const char *persona_json,
                const char *recent_prompts_json, const char *user_input);

/* Free a string returned by any of the above. */
void ctwin_string_free(char *s);

#ifdef __cplusplus
}
#endif

#endif /* COGNITIVE_TWIN_CORE_H */
