{{- define "fastapi-platform-foundation.labels" -}}
app.kubernetes.io/part-of: fastapi-microservices-platform
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
