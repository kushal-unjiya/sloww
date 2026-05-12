# Build stage
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json pnpm-lock.yaml* ./

RUN corepack enable \
  && pnpm install --frozen-lockfile

COPY . .

ARG VITE_CLERK_PUBLISHABLE_KEY
ARG VITE_APP_URL=http://localhost:8000
ENV VITE_CLERK_PUBLISHABLE_KEY=${VITE_CLERK_PUBLISHABLE_KEY}
ENV VITE_APP_URL=${VITE_APP_URL}

RUN pnpm build

# Runtime stage
FROM nginx:alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

