# Stage 1: Install dependencies and compile production build
FROM node:26-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# Stage 2: Standard optimized runtime environment
FROM node:26-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

# Copy built application assets and compiled artifacts
COPY --from=builder /app/package*.json ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Start Next.js in production mode
CMD ["npm", "start"]
