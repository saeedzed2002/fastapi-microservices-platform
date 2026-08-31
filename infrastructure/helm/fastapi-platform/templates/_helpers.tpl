{{- define "fastapi-platform.labels" -}}
app.kubernetes.io/part-of: fastapi-microservices-platform
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "fastapi-platform.image" -}}
{{- $root := index . 0 -}}
{{- $serviceName := index . 1 -}}
{{- $service := index $root.Values.images.services $serviceName | default (dict) -}}
{{- if $service.digest -}}
  {{- if not (regexMatch "^[a-f0-9]{64}$" $service.digest) -}}
    {{- fail (printf "images.services.%s.digest must contain exactly 64 lowercase hexadecimal characters" $serviceName) -}}
  {{- end -}}
  {{- printf "%s/%s@sha256:%s" $root.Values.images.repositoryPrefix $serviceName $service.digest -}}
{{- else if $service.tag -}}
  {{- if not $root.Values.images.allowMutableTags -}}
    {{- fail (printf "images.services.%s.tag is forbidden; use an immutable digest for delivery" $serviceName) -}}
  {{- end -}}
  {{- printf "%s/%s:%s" $root.Values.images.repositoryPrefix $serviceName $service.tag -}}
{{- else -}}
  {{- fail (printf "set images.services.%s.digest to an immutable release digest or tag for disposable conformance" $serviceName) -}}
{{- end -}}
{{- end }}

{{- define "fastapi-platform.imagePullSecrets" -}}
{{- with .Values.images.pullSecrets }}
imagePullSecrets:
  {{- range . }}
  - name: {{ . }}
  {{- end }}
{{- end }}
{{- end }}

{{- define "fastapi-platform.podSecurityContext" -}}
runAsNonRoot: true
runAsUser: 10001
runAsGroup: 10001
fsGroup: 10001
seccompProfile:
  type: RuntimeDefault
{{- end }}

{{- define "fastapi-platform.containerSecurityContext" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities:
  drop: ["ALL"]
{{- end }}

{{- define "fastapi-platform.runtimeEnvFrom" -}}
envFrom:
  - configMapRef:
      name: {{ .Values.runtime.configMapName }}
  - secretRef:
      name: {{ .Values.runtime.secretName }}
{{- end }}
