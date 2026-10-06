# Multi-stage Dockerfile for Next.js Dashboard

# Stage 1: Dependencies
FROM node:24-alpine AS deps
WORKDIR /app

# Install dependencies based on the preferred package manager
COPY package.json package-lock.json* ./
RUN npm ci

# Stage 2: Builder
FROM node:24-alpine AS builder
WORKDIR /app

# Copy dependencies from deps stage
COPY --from=deps /app/node_modules ./node_modules

# Copy all application files
COPY . ./

# Build arguments (passed from GitHub Actions or docker build)
ARG DATABASE_URL=postgresql://dummy:dummy@localhost:5432/dummy
# Inlined into the client bundle by Next, so it has to be present at build time.
ARG NEXT_PUBLIC_RUNNER_PORT=8080

# Set environment variables for build
ENV NEXT_TELEMETRY_DISABLED=1
ENV DATABASE_URL=${DATABASE_URL}
ENV NEXT_PUBLIC_RUNNER_PORT=${NEXT_PUBLIC_RUNNER_PORT}

# Build the application
RUN npm run build

# Stage 3: Runner (Production)
FROM node:24-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Create non-root user
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# Copy necessary files from builder
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
