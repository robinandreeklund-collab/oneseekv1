// Based on github.com/lightpanda-io/gomcp (Apache 2.0)
// Extended with additional schema types for richer tool definitions.

package mcp

type Schema any

type SchemaType struct {
	Type        string `json:"type"`
	Description string `json:"description"`
}

type schemaString SchemaType

func NewSchemaString(description string) schemaString {
	return schemaString(SchemaType{Type: "string", Description: description})
}

type schemaBoolean SchemaType

func NewSchemaBoolean(description string) schemaBoolean {
	return schemaBoolean(SchemaType{Type: "boolean", Description: description})
}

type schemaInteger SchemaType

func NewSchemaInteger(description string) schemaInteger {
	return schemaInteger(SchemaType{Type: "integer", Description: description})
}

// schemaEnum represents a string enum schema.
type schemaEnum struct {
	Type        string   `json:"type"`
	Description string   `json:"description"`
	Enum        []string `json:"enum"`
}

func NewSchemaEnum(description string, values []string) schemaEnum {
	return schemaEnum{Type: "string", Description: description, Enum: values}
}

// schemaObjectField represents a nested object schema with properties.
type schemaObjectField struct {
	Type                 string     `json:"type"`
	Description          string     `json:"description"`
	AdditionalProperties bool       `json:"additionalProperties"`
	Properties           Properties `json:"properties,omitempty"`
}

func NewSchemaObjectField(description string) schemaObjectField {
	return schemaObjectField{
		Type:                 "object",
		Description:          description,
		AdditionalProperties: true,
	}
}

type Properties map[string]Schema

type schemaObject struct {
	SchemaType
	Properties           Properties `json:"properties"`
	AdditionalProperties bool       `json:"additionalProperties"`
	Required             []string   `json:"required,omitempty"`
}

func NewSchemaObject(p map[string]Schema) schemaObject {
	return schemaObject{
		SchemaType: SchemaType{Type: "object"},
		Properties: p,
	}
}

func NewSchemaObjectRequired(p map[string]Schema, required []string) schemaObject {
	return schemaObject{
		SchemaType: SchemaType{Type: "object"},
		Properties: p,
		Required:   required,
	}
}

type Tool struct {
	Name        string       `json:"name"`
	Description string       `json:"description,omitempty"`
	InputSchema schemaObject `json:"inputSchema"`
}
