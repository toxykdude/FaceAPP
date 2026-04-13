# PowerHouse Membership Platform - Frontend

Modern React admin dashboard for the PowerHouse Membership Platform.

## Features

- **Authentication**: JWT-based login with protected routes
- **Member Management**: CRUD operations with search and filtering
- **Facial Enrollment**: Webcam integration for biometric enrollment
- **Membership Management**: Subscription tracking with access rules
- **Sales & Transactions**: Payment processing and invoice generation
- **Camera Monitoring**: RTSP camera configuration and status
- **Reports & Analytics**: Revenue charts and access statistics
- **Responsive Design**: Mobile-friendly Material-UI interface

## Tech Stack

- **Framework**: React 18 with TypeScript
- **Build Tool**: Vite
- **UI Library**: Material-UI (MUI) v5
- **Routing**: React Router v6
- **State Management**: React Context API + React Query
- **Forms**: React Hook Form + Zod validation
- **HTTP Client**: Axios
- **Charts**: Recharts

## Prerequisites

- Node.js 18+ and npm
- Backend API running on http://localhost:8000

## Installation

### 1. Install Dependencies

```bash
cd frontend
npm install
```

### 2. Configure Environment

Create `.env` file:

```bash
cp .env.example .env
```

Edit `.env`:

```bash
VITE_API_URL=http://localhost:8000/api
```

### 3. Run Development Server

```bash
npm run dev
```

The application will be available at http://localhost:3000

## Project Structure

```
frontend/
├── src/
│   ├── api/                  # API client and methods
│   │   ├── client.ts        # Axios instance with interceptors
│   │   ├── auth.ts          # Authentication API
│   │   ├── members.ts       # Members API
│   │   └── ...
│   ├── components/          # Reusable components
│   │   ├── Layout/          # Layout components
│   │   │   └── MainLayout.tsx
│   │   └── ProtectedRoute.tsx
│   ├── contexts/            # React contexts
│   │   └── AuthContext.tsx  # Authentication state
│   ├── pages/               # Page components
│   │   ├── Login.tsx
│   │   ├── Dashboard.tsx
│   │   └── Members/
│   │       ├── MembersList.tsx
│   │       └── MemberForm.tsx
│   ├── theme/               # MUI theme configuration
│   │   └── index.ts
│   ├── App.tsx              # Root component with routing
│   ├── main.tsx             # Application entry point
│   └── index.css            # Global styles
├── package.json
├── vite.config.ts
└── tsconfig.json
```

## Available Scripts

```bash
# Development server
npm run dev

# Production build
npm run build

# Preview production build
npm run preview

# Type checking
npm run type-check

# Linting
npm run lint
```

## Default Credentials

- **Username**: `admin`
- **Password**: `admin123`

⚠️ Change the admin password after first login!

## Features Guide

### Authentication

- Login page with form validation
- JWT token storage in localStorage
- Automatic token injection in API requests
- Protected routes with redirect to login
- Logout functionality

### Member Management

- **List View**: Paginated table with search
- **Create**: Form with validation
- **Edit**: Pre-filled form with member data
- **Delete**: Confirmation dialog
- **Biometric Enrollment**: Webcam integration (coming soon)

### Dashboard

- Active members count
- Today's check-ins
- Monthly revenue
- Recent access events

### Responsive Design

- Desktop: Full sidebar navigation
- Tablet: Collapsible sidebar
- Mobile: Drawer navigation

## API Integration

The frontend communicates with the backend API using Axios:

```typescript
// Example API call
import { membersApi } from '@/api/members';

const members = await membersApi.getMembers({
  skip: 0,
  limit: 25,
  search: 'john',
});
```

### API Client Features

- Automatic JWT token injection
- Request/response interceptors
- Error handling
- 401 redirect to login
- TypeScript interfaces

## State Management

### Authentication State

Managed by `AuthContext`:

```typescript
const { user, isAuthenticated, login, logout } = useAuth();
```

### Server State

Managed by React Query:

```typescript
const { data, isLoading } = useQuery({
  queryKey: ['members'],
  queryFn: () => membersApi.getMembers(),
});
```

## Form Validation

Using React Hook Form + Zod:

```typescript
const schema = z.object({
  email: z.string().email(),
  phone: z.string().min(1),
});

const { control, handleSubmit } = useForm({
  resolver: zodResolver(schema),
});
```

## Styling

Material-UI components with custom theme:

```typescript
// Custom theme in src/theme/index.ts
const theme = createTheme({
  palette: {
    primary: { main: '#1976d2' },
    secondary: { main: '#dc004e' },
  },
});
```

## Development Tips

### Hot Module Replacement

Vite provides instant HMR for fast development:
- Changes reflect immediately
- State is preserved when possible

### TypeScript

Strict mode enabled for type safety:
- All API responses typed
- Component props typed
- Form data typed

### Path Aliases

Use `@/` for imports:

```typescript
import { useAuth } from '@/contexts/AuthContext';
import { membersApi } from '@/api/members';
```

## Building for Production

```bash
npm run build
```

Output in `dist/` directory:
- Optimized bundles
- Code splitting
- Tree shaking
- Minification

### Deployment

Deploy `dist/` folder to:
- Nginx
- Apache
- Netlify
- Vercel
- AWS S3 + CloudFront

### Environment Variables

For production, set:

```bash
VITE_API_URL=https://api.yourdomain.com/api
```

## Troubleshooting

### API Connection Error

```bash
# Check backend is running
curl http://localhost:8000/api/health

# Verify CORS settings in backend
# Check .env VITE_API_URL
```

### Build Errors

```bash
# Clear node_modules and reinstall
rm -rf node_modules package-lock.json
npm install

# Clear Vite cache
rm -rf node_modules/.vite
```

### TypeScript Errors

```bash
# Run type checking
npm run type-check

# Check tsconfig.json paths
```

## Browser Support

- Chrome (latest)
- Firefox (latest)
- Edge (latest)
- Safari (latest)

## Performance

- Code splitting by route
- Lazy loading for heavy components
- React Query caching
- Optimized bundle size

## Security

- JWT tokens in localStorage
- HTTPS required for production
- XSS protection via React
- CSRF protection via backend

## Future Enhancements

- [ ] Real-time event feed (WebSocket)
- [ ] Facial enrollment interface
- [ ] Camera live preview
- [ ] Export reports (CSV, PDF)
- [ ] Dark mode toggle
- [ ] Multi-language support

## License

Proprietary - PowerHouse Membership Platform
